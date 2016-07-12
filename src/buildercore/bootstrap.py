__description__ = """Logic for provisioning and bootstrapping an automatically
created Cloudformation template.

The "stackname" parameter these functions take is the name of the cfn template
without the extension."""

import os, shutil
from os.path import join
from functools import partial
from StringIO import StringIO
from . import core, utils, config, s3, keypair
from .core import connect_aws_with_stack, stack_pem, stack_conn, project_data_for_stackname
from .utils import first
from .config import DEPLOY_USER, BOOTSTRAP_USER
from .decorators import osissue, osissuefn
from fabric.api import env, local, settings, run, sudo, cd, put, get
import fabric.exceptions as fabric_exceptions
from fabric.contrib import files
from contextlib import contextmanager
from boto.exception import BotoServerError
from kids.cache import cache as cached

import logging
LOG = logging.getLogger(__name__)

#
#
#

@contextmanager
def master_server(region, username=BOOTSTRAP_USER):
    """connects to the master server in the specified region. 

    you can only connect to the master server if you have access 
    to the master server  private key or you're in it's authorized 
    users list"""
    # should you *really* be trying to access the master?
    master_stackname = core.find_master(region)
    kwargs = {
        'user': username,
        'host_string': master(region, 'ip_address'),
        'key_filename': stack_pem(master_stackname, die_if_doesnt_exist=True),
        'abort_on_prompts': True,
    }
    with settings(**kwargs):
        yield

#
# provision stack
#

#@requires_stack_file
def create_stack(stackname):
    "simply creates the stack of resources on AWS. call `bootstrap_stack` to install/update software on the stack."
    LOG.info('creating stack %r', stackname)
    stack_body = core.stack_json(stackname)
    try:
        keypair.create_keypair(stackname)
        conn = connect_aws_with_stack(stackname, 'cfn')
        conn.create_stack(stackname, stack_body, parameters=[('KeyName', stackname)])
        def is_updating(stackname):
            return core.describe_stack(stackname).stack_status in ['CREATE_IN_PROGRESS']
        utils.call_while(partial(is_updating, stackname), update_msg='Waiting for AWS to finish creating stack ...')
        return True
    except BotoServerError as err:
        if err.message.endswith(' already exists'):
            LOG.debug(err.message)
            return False
        # don't delete the keypair if the error is that the stack already exists!
        keypair.delete_keypair(stackname)
        raise
    except:
        keypair.delete_keypair(stackname)
        raise

#@requires_stack_file
#@requires_active_stack
def update_template(stackname):
    "updates the CloudFormation stack and then updates the environment"
    LOG.info("updating stack %s", stackname)
    try:
        stackbody = core.stack_json(stackname)
        conn = connect_aws_with_stack(stackname, 'cfn')
        conn.update_stack(stackname, stackbody, parameters=[('KeyName', stackname)])
        def is_updating(stackname):
            return core.describe_stack(stackname).stack_status in \
              ['UPDATE_IN_PROGRESS', 'UPDATE_IN_PROGRESS_CLEANUP_IN_PROGRESS']
        utils.call_while(partial(is_updating, stackname), update_msg='Waiting for AWS to finish updating stack')
    except BotoServerError as err:
        if err.message.endswith('No updates are to be performed.'):
            print err.message
        else:
            LOG.exception("unhandled exception attempting to update stack")
            raise

def update_all(region):
    "updates *all* minions talking to the master. this is *really* not recommended."
    with master_server(region, username=config.DEPLOY_USER):
        run("service salt-minion restart")
        run(r"salt \* state.highstate --retcode-passthrough")


#
#  attached stack resources, ec2 data
#

@core.requires_active_stack
def stack_resources(stackname):
    "returns a list of resources provisioned by the given stack"
    return connect_aws_with_stack(stackname, 'cfn').describe_stack_resources(stackname)

def ec2_instance_data(stackname):
    "returns the ec2 instance data from the first ec2 instance the stack has"
    ec2 = first([r for r in stack_resources(stackname) if r.resource_type == "AWS::EC2::Instance"])
    conn = connect_aws_with_stack(stackname, 'ec2')
    return conn.get_only_instances([ec2.physical_resource_id])[0]

@cached
def master_data(region):
    "returns the ec2 instance data for the master-server"
    stackname = core.find_master(region)
    return ec2_instance_data(stackname)

def master(region, key):
    return getattr(master_data(region), key)

#
# bootstrap stack
#

@core.requires_active_stack
def template_info(stackname):
    "returns some useful information about the given stackname as a map"
    conn = connect_aws_with_stack(stackname, 'cfn')
    data = conn.describe_stacks(stackname)[0].__dict__
    data['outputs'] = reduce(utils.conj, map(lambda o: {o.key: o.value}, data['outputs']))
    return utils.exsubdict(data, ['connection', 'parameters'])

#
# minion private/public key wrangling
#

def remote_stack_key_exist(stackname):
    "ask master if the key for the given stack exists."
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    with master_server(region):
        # /etc/salt/pki/master/minions/master-server-2015-31-12.pub
        return files.exists('/etc/salt/pki/master/minions/%s' % stackname, use_sudo=True)

@core.requires_stack_file
def local_stack_keys_exist(stackname):
    """once the Salt master has generated keys for the minion they
    are downloaded and live alongside the stack template directory.
    returns True if both a public and private key are found locally
    for the given stack"""
    fname_list = [
        '%s.pub' % stackname, # master-server-2015-31-12.pub
        '%s.pem' % stackname  # master-server-2015-31-12.pem
    ]
    # look in the same directory as the stack
    stack_path = os.path.dirname(core.stack_path(stackname))
    return all([os.path.exists(join(stack_path, fname)) for fname in fname_list])

def generate_stack_keys(stackname):
    """pre-seeds minion keys on the master

    The master Salt server needs to identify connections as coming from a known minion.

    A public and private key-pair are generated on the master server.
    The public key is copied into the master's directory of known minion public keys.
    The keys are then downloaded and live alongside the stack template json files."""
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    with master_server(region):
        kwargs = {'stackname': stackname, 'bootstrap_user': BOOTSTRAP_USER}
        # remember, stackname == minion-id
        cmds = [
            "salt-key --gen-keys=%(stackname)s" % kwargs,
            "mkdir -p /etc/salt/pki/master/minions/",
            "cp %(stackname)s.pub /etc/salt/pki/master/minions/%(stackname)s" % kwargs, 
            # prep keys for download
            "chown %(bootstrap_user)s:%(bootstrap_user)s %(stackname)s.*" % kwargs,
            "chmod 600 %(stackname)s.pem" % kwargs
        ]
        map(sudo, cmds)

        # generate stack keys in same dir as stack
        stack_path = core.stack_path(stackname) # ll: /foo/bar/stackname.json
        stack_dir = os.path.dirname(stack_path) # ll: /foo/bar/
        stack_stub = join(stack_dir, stackname) # ll: /foo/bar/stackname  (with no ext)
        # download the public and private keys and make private key read-only
        local("rm -f %s.p*" % stack_stub) # nuke any existing keys
        
        # UNTESTED. all that download code had to go though
        #download(stack_dir, [stackname+'.pub', stackname+'.pem'])
        files_to_download = [stackname+'.pub', stackname+'.pem']
        map(get, files_to_download)
        
        local("chmod 640 %s.pem" % stack_stub)

#pylint: disable=invalid-name
def generate_stack_keys_if_necessary(stackname):
    """checks the master if the pub+pem keys exist irregardless if the keys 
    exist locally.

    the master may have been destroyed and resurrected since creation.
    its also possible the keys were successfully generated remotely but 
    were not properly downloaded"""
    remote_exists = remote_stack_key_exist(stackname) # master server
    local_exists = local_stack_keys_exist(stackname)  # your machine
    if not remote_exists or not local_exists:
        if not remote_exists:
            LOG.info("remote stack keys not found.")
        if not local_exists:
            LOG.info("local stack keys not found.")
        LOG.info("either the remote or local stack keys were not found. generating anew")
        generate_stack_keys(stackname)
        LOG.warn("generating stack keys")
    else:
        LOG.info("found both local and remote stack keys. skipping generation")

def write_environment_info(stackname):
    """Looks for /etc/cfn-info.json and writes one if not found.
    Must be called with an active stack connection."""
    if not files.exists("/etc/cfn-info.json"):
        LOG.info('no cfn-outputs found, writing ...')
        infr_config = utils.json_dumps(template_info(stackname))
        return put(StringIO(infr_config), "/etc/cfn-info.json", use_sudo=True)
    LOG.info('cfn-outputs found, skipping')
    return []

#
#
#

@core.requires_active_stack
def update_stack(stackname):
    """installs/updates the ec2 instance attached to the specified stackname.

    once AWS has finished creating an EC2 instance for us, we need to install 
    Salt and get it talking to the master server. Salt comes with a bootstrap 
    script that can be downloaded from the web and then very conveniently 
    installs it's own dependencies. Once Salt is installed we give it an ID 
    (the given `stackname`), the address of the master server """
    pdata = core.project_data_for_stackname(stackname)
    public_ip = ec2_instance_data(stackname).ip_address
    region = pdata['aws']['region']

    is_master = core.is_master_server_stack(stackname)

    # not necessary on update, but best to check.
    #generate_stack_keys_if_necessary(stackname)

    # we have an issue where the stack is created, however the security group
    # hasn't been attached or similar, or ssh isn't running and we can't get in.
    # this waits until a connection can be made and a file is found before continuing.
    def is_resourcing():
        try:
            with stack_conn(stackname, username=BOOTSTRAP_USER):
                # call until file exists
                return not files.exists(join('/home', BOOTSTRAP_USER))
        except fabric_exceptions.NetworkError:
            LOG.debug("failed to connect to server ...")
            return True
    utils.call_while(is_resourcing, interval=3, update_msg='waiting for /home/ubuntu to be detected ...')

    def run_script(script_path, *script_params):
        "uploads a script for SCRIPTS_PATH and executes it in the /tmp dir with given params"
        local_script = join(config.SCRIPTS_PATH, script_path)
        remote_script = join('/tmp', os.path.basename(script_path))
        put(local_script, remote_script)
        cmd = ["/bin/bash", remote_script] + list(script_params)
        retval = sudo(" ".join(cmd))
        sudo("rm " + remote_script) # remove the script after executing it
        return retval

    # forward-agent == ssh -A
    with stack_conn(stackname, username=BOOTSTRAP_USER, forward_agent=True):
        # upload the private key if present
        if not files.exists("/root/.ssh/id_rsa", use_sudo=True):
            # if this file doesn't exist remotely, upload it.
            # if it also doesn't exist on the filesystem, die horribly.
            # regular updates shouldn't have to deal with this.
            put(stack_pem(stackname, die_if_doesnt_exist=True), "/root/.ssh/id_rsa", use_sudo=True)

        # write out environment config so Salt can read CFN outputs
        write_environment_info(stackname)

        salt_version = pdata['salt']
        install_master_flag = str(is_master).lower()
        master_ip = master(region, 'private_ip_address')

        run_script('bootstrap.sh', salt_version, stackname, install_master_flag, master_ip)
        if is_master:
            run_script('init-master.sh', stackname, pdata['formula-repo'])

        sudo('salt-call state.highstate --retcode-passthrough') # this will tell the machine to update itself

@core.requires_stack_file
def delete_stack_file(stackname):
    try:
        core.describe_stack(stackname) # triggers exception if NOT exists
        LOG.warning('stack %r still exists, refusing to delete stack files. delete active stack first.', stackname)
        return
    except BotoServerError, ex:
        if not ex.message.endswith('does not exist'):
            LOG.exception("unhandled exception attempting to confirm if stack %r exists", stackname)
            raise
    ext_list = [
        ".pem",
        ".pub",
        ".json",
        ".yaml", # yaml files are now deprecated
    ]
    paths = [join(config.STACK_DIR, stackname + ext) for ext in ext_list]
    paths = filter(os.path.exists, paths)
    def _unlink(path):
        os.unlink(path)
        return not os.path.exists(path)
    return dict(zip(paths, map(_unlink, paths)))

def delete_stack(stackname):
    try:
        connect_aws_with_stack(stackname, 'cfn').delete_stack(stackname)
        def is_deleting(stackname):
            try:
                return core.describe_stack(stackname).stack_status in ['DELETE_IN_PROGRESS']
            except BotoServerError as err:
                if err.message.endswith('does not exist'):
                    return False
                raise # not sure what happened, but we're not handling it here. die.
        utils.call_while(partial(is_deleting, stackname), update_msg='Waiting for AWS to finish deleting stack ...')
        keypair.delete_keypair(stackname)
        delete_stack_file(stackname)
        LOG.info("stack %r deleted", stackname)
    except BotoServerError as err:
        LOG.exception("[%s: %s] %s (request-id: %s)", err.status, err.reason, err.message, err.request_id)
