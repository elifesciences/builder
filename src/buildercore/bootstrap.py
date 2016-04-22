__description__ = """Logic for provisioning and bootstrapping an automatically
created Cloudformation template.

The "stackname" parameter these functions take is the name of the cfn template
without the extension."""

import os
from os.path import join
from functools import partial
from StringIO import StringIO
from . import core, utils, config
from .core import boto_cfn_conn, deploy_user_pem, stack_conn
from .utils import first
from .sync import sync_private, sync_stack, do_sync
from .config import DEPLOY_USER, BOOTSTRAP_USER

from fabric.api import env, local, settings, run, sudo, cd, put
import fabric.exceptions as fabric_exceptions
from fabric.contrib import files
from contextlib import contextmanager
from boto.exception import BotoServerError

import logging
LOG = logging.getLogger(__name__)

@contextmanager
def master_server(username=BOOTSTRAP_USER):
    with settings(user=username, host_string=master('ip_address'), key_filename=deploy_user_pem()):
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
        if core.old_stack(stackname):
            # TODO: once all stacks are updated, remove this
            boto_cfn_conn().create_stack(stackname, stack_body, parameters=[('KeyName', 'deploy-user')])
        else:
            boto_cfn_conn().create_stack(stackname, stack_body)
        def is_updating(stackname):
            return core.describe_stack(stackname).stack_status in ['CREATE_IN_PROGRESS']
        utils.call_while(partial(is_updating, stackname), update_msg='Waiting for AWS to finish creating stack ...')
        return True
    except BotoServerError as err:
        if err.message.endswith(' already exists'):
            LOG.debug(err.message)
            return False
        raise

#@requires_stack_file
#@requires_active_stack
def update_template(stackname):
    "updates the CloudFormation stack and then updates the environment"
    LOG.info("updating stack %s", stackname)
    try:
        stackbody = core.stack_json(stackname)
        if core.old_stack(stackname):
            boto_cfn_conn().update_stack(stackname, stackbody, parameters=[('KeyName', 'deploy-user')])
        else:
            boto_cfn_conn().update_stack(stackname, stackbody)
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

def update_master():
    "updates the elife-builder on the master and restarts the salt-master"
    with master_server(username=config.DEPLOY_USER):
        with cd('/opt/elife/elife-builder/'):
            utils.git_purge()
            utils.git_update()
            sudo('service salt-master restart')

def update_master_fully():
    "does a complete update of the master server, updating the template, the elife-builder and it's environment"
    # NOTE: the master is bootstrapped as the 'ubuntu' user before the deploy user ever exists.
    master_template = core.find_master()
    update_template(master_template)
    update_master()
    update_environment(master_template)

def update_all():
    "updates *all* minions talking to the master. this is *really* not recommended."
    update_master()
    with master_server(username=config.DEPLOY_USER):
        run("service salt-minion restart")
        run(r"salt \* state.highstate")


#
#  attached stack resources, ec2 data
#

@core.requires_active_stack
def stack_resources(stackname):
    "returns a list of resources provisioned by the given stack"
    return boto_cfn_conn().describe_stack_resources(stackname)

def ec2_instance_data(stackname):
    "returns the ec2 instance data from the first ec2 instance the stack has"
    ec2 = first([r for r in stack_resources(stackname) if r.resource_type == "AWS::EC2::Instance"])
    ec2conn = core.boto_ec2_conn()
    return ec2conn.get_only_instances([ec2.physical_resource_id])[0]

@utils.cached
def master_data():
    "returns the ec2 instance data for the master-server"
    return ec2_instance_data(core.find_master())

def master(key):
    return getattr(master_data(), key)

'''
# TODO: delete? this function is *so* clever but isn't actually being used?? wtf luke.
@core.requires_active_stack
def run_commands(stackname, cmd_list, continue_on_fail=False):

    
    def rc(cmds, continue_on_fail=False):
        "recursively run a series of commands. if the command is a 'cd' command, it sets up a context manager"
        fcmd = first(cmds)
        rcmds = rest(cmds)
        if fcmd.lstrip().startswith('cd ') and rcmds:
            with cd(fcmd.lstrip('cd ')):
                # run the rest of the command within this context
                return rc(rcmds, continue_on_fail)
        
        retobj = sudo(fcmd)
        retval = retobj.return_code
        if retval != 0:
            LOG.warn("command failed: %r", fcmd)
            if not continue_on_fail:
                LOG.error("a command has failed and all commands must pass. not continue.")
        
        if rcmds:
            return rc(rcmds, continue_on_fail)
        
        return retval

    ec2 = ec2_instance_data(stackname)    
    with settings(user=config.DEPLOY_USER, host_string=ec2.ip_address, key_filename=deploy_user_pem()):
        with settings(warn_only=True): # prevent Fabric raising SystemExit
            return rc(cmd_list, continue_on_fail)
'''


#
# bootstrap stack
#

def copy(src, dest, use_sudo=False, unsafe=False):
    with settings(user=DEPLOY_USER, host_string=env.host_string, key_filename=deploy_user_pem()):
        cmd = "cp %s %s" % (src, dest)
        func = sudo if use_sudo else run
        func(cmd)
        if unsafe:
            # make world-readable
            sudo("chmod +r %s" % dest)
        return dest

def scp(direction, ffile, dest_fname, host=None, user=DEPLOY_USER):
    "scp a list of files up and down between the client and the given destination "
    assert direction in ['up', 'down'], LOG.error("unknown direction %r", direction)
    kwargs = {'pem': deploy_user_pem(),
              'user': user,
              'host': host or env.host_string,
              'file': ffile,
              'dest': dest_fname,
              'ssh-args': " ".join(["-o StrictHostKeyChecking=no",
                                    "-o UserKnownHostsFile=/dev/null"])}
    if direction == 'down':
        tem = "scp -i %(pem)s %(ssh-args)s '%(user)s@%(host)s:%(file)s' %(dest)s"
    else:
        tem = "scp -i %(pem)s %(ssh-args)s %(file)s '%(user)s@%(host)s:%(dest)s'"
    return local(tem % kwargs)

@osissue("embarassing code. refactor. replace with fabric's `get` and `put`")
def download(dest, file_list, as_user=BOOTSTRAP_USER):
    download_user = DEPLOY_USER if as_user == config.ROOT_USER else as_user
    def _download(fname):
        dest_fname = fname
        if isinstance(fname, tuple):
            # given destination can be overriden if filename is a tuple of (src, dest) 
            fname, dest_fname = fname
        if as_user == config.ROOT_USER:
            # copy the file (as root) to a dir that can be read for downloading
            # looks like: /tmp/bar.xml
            fname = copy(fname, join("/tmp/", os.path.basename(fname)), use_sudo=True, unsafe=True)
        dest_fname = join(dest, dest_fname)
        dest_dir = os.path.dirname(dest_fname)
        if not os.path.exists(dest_dir):
            local("mkdir -p %s" % dest_dir)
        scp('down', fname, dest_fname, user=download_user)
    return map(_download, file_list)

@core.requires_active_stack
def template_info(stackname):
    "returns some useful information about the given stackname as a map"
    data = core.boto_cfn_conn().describe_stacks(stackname)[0].__dict__
    data['outputs'] = reduce(utils.conj, map(lambda o: {o.key: o.value}, data['outputs']))
    return utils.exsubdict(data, ['connection', 'parameters'])

#
# minion private/public key wrangling
#

def remote_stack_key_exist(stackname):
    "ask master if the key for the given stack exists."
    with master_server():
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

@sync_stack
def generate_stack_keys(stackname):
    """pre-seeds minion keys on the master

    The master Salt server needs to identify connections as coming from a known minion.

    A public and private key-pair are generated on the master server.
    The public key is copied into the master's directory of known minion public keys.
    The keys are then downloaded and live alongside the stack template json files."""
    with master_server():
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
        download(stack_dir, [stackname+'.pub', stackname+'.pem'])
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
def update_environment(stackname):
    """installs/updates the ec2 instance attached to the specified stackname.

    once AWS has finished creating an EC2 instance for us, we need to install 
    Salt and get it talking to the master server. Salt comes with a bootstrap 
    script that can be downloaded from the web and then very conveniently 
    installs it's own dependencies. Once Salt is installed we give it an ID 
    (the given `stackname`), the address of the master server """
    pdata = core.project_data_for_stackname(stackname)
    public_ip = ec2_instance_data(stackname).ip_address

    # not necessary on update, but best to check.
    generate_stack_keys_if_necessary(stackname)

    # we have an issue where the stack is created, however the security group
    # hasn't been attached or similar, or ssh isn't running and we can't get in.
    # this waits until a connection can be made and a file is found before continuing.
    def is_resourcing():
        try:
            with settings(user=BOOTSTRAP_USER, host_string=public_ip, key_filename=deploy_user_pem()):
                # calluntil file exists
                return not files.exists(join('/home', BOOTSTRAP_USER))
        except fabric_exceptions.NetworkError:
            LOG.debug("failed to connect to server ...")
            return True
    utils.call_while(is_resourcing, interval=3, update_msg='waiting for /home/ubuntu to be detected ...')

    with stack_conn(stackname, username=BOOTSTRAP_USER):
        # upload bootstrap script
        remote_script = '/tmp/.bootstrap.sh'
        local_script = open(join(config.SCRIPTS_PATH, 'bootstrap.sh'), 'r')
        put(local_script, remote_script)
        # run it with the project's specified version of Salt
        sudo("/bin/bash %s %s" % (remote_script, pdata['salt']))

        LOG.info("salt is now installed")
        
        # overwrite stale minion data in ami created instances
        LOG.info("replacing minion file")
        map(sudo, [
            "echo 'master: %s' > /etc/salt/minion" % master('ip_address'), 
            "echo 'id: %s' >> /etc/salt/minion" % stackname,
        ])

        # write out environment config so Salt can read CFN outputs
        write_environment_info(stackname)

        # only upload keys if we can't find them
        if not files.exists("/etc/salt/pki/minion/minion.pem") \
          or not files.exists("/etc/salt/pki/minion/minion.pub"):

            LOG.info("minion doesn't look like it can talk to master yet. configuring.")

            # create and upload payload
            stack_path = os.path.dirname(core.stack_path(stackname, relative=True))
            kwargs = {'private_dir': config.PRIVATE_DIR, 'stack_dir': stack_path, 'stackname': stackname}
            local('tar cvzf /tmp/private.tar.gz %(private_dir)s/ %(stack_dir)s/%(stackname)s.p*' % kwargs)
            put("/tmp/private.tar.gz", remote_path="~/")
            local('rm /tmp/private.tar.gz')

            # remotely unpack payload and move files to their new homes 
            run('tar xvzf private.tar.gz')
            # give the root and bootstrap (ubuntu) users the deploy-user's private key. BAD
            sudo('cp -f /home/%s/private/deploy-user.pem /root/.ssh/id_rsa && chmod 400 /root/.ssh/id_rsa' % BOOTSTRAP_USER)
            run('mv -f private/deploy-user.pem .ssh/id_rsa && chmod 400 .ssh/id_rsa')

            # distribute minion's keys
            sudo('mv -f %(stack_dir)s/%(stackname)s.pem /etc/salt/pki/minion/minion.pem' % kwargs)
            sudo('mv -f %(stack_dir)s/%(stackname)s.pub /etc/salt/pki/minion/minion.pub' % kwargs)

            # destroy the payload
            run('rm -rf %(private_dir)s/ %(stack_dir)s payload.tar.gz' % kwargs)

        else:
            LOG.info("found minion keys, skipping uploading to master.")

        # tell the instance to update itself
        map(sudo, [
            'service salt-minion restart',
            'salt-call state.highstate', # this will tell the machine to update itself
        ])

def update_stack(stackname):
    "convenience. updates the master with the latest builder code, then updates the specified instance"
    update_master()
    return update_environment(stackname)


@core.requires_stack_file
@sync_stack
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
        boto_cfn_conn().delete_stack(stackname)
        def is_deleting(stackname):
            try:
                return core.describe_stack(stackname).stack_status in ['DELETE_IN_PROGRESS']
            except BotoServerError as err:
                if err.message.endswith('does not exist'):
                    return False
                raise # not sure what happened, but we're not handling it here. die.
        utils.call_while(partial(is_deleting, stackname), update_msg='Waiting for AWS to finish deleting stack ...')
        delete_stack_file(stackname)
        LOG.info("stack %r deleted", stackname)
    except BotoServerError as err:
        LOG.exception("[%s: %s] %s (request-id: %s)", err.status, err.reason, err.message, err.request_id)
