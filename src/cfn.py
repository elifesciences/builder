from distutils.util import strtobool
from fabric.api import task, local, settings, run, sudo, put, get, abort
from fabric.api import task, local, settings, run, sudo, put, get, abort
from fabric.contrib import files
import aws, utils
from decorators import requires_project, requires_aws_stack, requires_steady_stack, echo_output, setdefault, debugtask
from buildercore import core, cfngen, utils as core_utils, bootstrap, project, checks
from buildercore.core import stack_conn, stack_pem
from buildercore.decorators import PredicateException
from buildercore.config import DEPLOY_USER, BOOTSTRAP_USER
from distutils.util import strtobool
import os

import logging
LOG = logging.getLogger(__name__)

# these aliases are deprecated
@task(alias='aws_delete_stack')
@requires_steady_stack
def destroy(stackname):
    "tell aws to delete a stack."
    print 'this is a BIG DEAL. you cannot recover from this.'
    print 'type the name of the stack to continue or anything else to quit'
    uin = raw_input('> ')
    if not uin or not uin.strip().lower() == stackname.lower():
        import difflib
        print 'you needed to type "%s" to continue.' % stackname
        print 'got:'
        print '\n'.join(difflib.ndiff([stackname], [uin]))
        exit(1)
    return bootstrap.delete_stack(stackname)

@task
def ensure_destroyed(stackname):
    try:
        return bootstrap.delete_stack(stackname)
    except PredicateException as e:
        if "I couldn't find a cloudformation stack" in str(e):
            print "Not even the CloudFormation template exists anymore, exiting idempotently"
            return
        raise

# these aliases are deprecated
@task(alias='aws_update_stack')
@requires_aws_stack
def update(stackname):
    """Updates the environment within the stack's ec2 instance. 

    does *not* call Cloudformation's `update` command on the stack"""
    return bootstrap.update_stack(stackname)

@task
def update_master():
    return bootstrap.update_stack(core.find_master(aws.find_region()))

@requires_project
def generate_stack_from_input(pname, instance_id=None):
    """creates a new CloudFormation file for the given project."""
    if not instance_id:
        default_instance_id = core_utils.ymd()
        instance_id = utils.uin("instance id", default_instance_id)
    stackname = core.mk_stackname(pname, instance_id)
    more_context = {'stackname': stackname}

    # prompt user for alternate configurations
    pdata = project.project_data(pname)
    if pdata.has_key('aws-alt'):
        def helpfn(altkey):
            try:
                return pdata['aws-alt'][altkey]['description']
            except KeyError:
                return None
        default = 'skip this step'
        alt_config = [default] + pdata['aws-alt'].keys()
        alt_config = utils._pick('alternative config', alt_config, helpfn=helpfn)
        if alt_config != default:
            more_context['alt-config'] = alt_config
    cfngen.generate_stack(pname, **more_context)
    return stackname

# these aliases are deprecated
@task(alias='aws_launch_instance')
@requires_project
def launch(pname, instance_id=None):
    try:
        stackname = generate_stack_from_input(pname, instance_id)
        pdata = core.project_data_for_stackname(stackname)

        print 'attempting to create stack:'
        print '  stackname: ' + stackname
        print '  region:    ' + pdata['aws']['region']
        print

        if core.is_master_server_stack(stackname):
            if not checks.can_access_builder_private(pname):
                print "failed to access your organisation's 'builder-private' repository:"
                print '  ' + pdata['private-repo']
                print "you'll need access to this repository to add a deploy key later"
                print
                return
        
        bootstrap.create_update(stackname)        
        setdefault('.active-stack', stackname)
    except core.NoMasterException, e:
        LOG.warn(e.message)
        print "\n%s\ntry `./bldr master.create`'" % e.message

@debugtask
@requires_aws_stack
def highstate(stackname):
    "a fast update with many caveats. prefer `update` instead"
    with stack_conn(stackname, username=BOOTSTRAP_USER):
        bootstrap.run_script('highstate.sh')
        
@debugtask
@requires_aws_stack
def pillar(stackname):
    "returns the pillar data a minion is using"
    with stack_conn(stackname, username=BOOTSTRAP_USER):
        sudo('salt-call pillar.items')
    
@debugtask
@echo_output
def aws_stack_list():
    "returns a list of realized stacks. does not include deleted stacks"
    region = aws.find_region()
    return core.active_stack_names(region)

@task
@requires_aws_stack
def ssh(stackname, username=DEPLOY_USER):
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    local("ssh %s@%s" % (username, public_ip))

@task
@requires_aws_stack
def owner_ssh(stackname):
    "maintainence ssh. uses the pem key and the bootstrap user to login."
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    # -i identify file
    local("ssh %s@%s -i %s" % (BOOTSTRAP_USER, public_ip, stack_pem(stackname)))
        
@task
@requires_aws_stack
def download_file(stackname, path, destination, allow_missing="False", use_bootstrap_user="False"):
    """
    Downloads `path` from `stackname` putting it into the `destination` folder, or the `destination` file if it exists and it is a file.

    If `allow_missing` is "True", a not existing `path` will be skipped without errors.

    If `use_bootstrap_user` is "True", the owner_ssh user will be used for connecting instead of the standard deploy user.

    Boolean arguments are expressed as strings as this is the idiomatic way of passing them from the command line.
    """
    fname = os.path.basename(path)
    utils.mkdirp(destination)
    with stack_conn(stackname, username=_user(use_bootstrap_user)):
        if _should_be_skipped(path, allow_missing):
            return
        get(path, destination, use_sudo=True)


@task
@requires_aws_stack
def upload_file(stackname, local_path, remote_path, overwrite=False):
    with stack_conn(stackname):
        print 'stack:',stackname
        print 'local:',local_path
        print 'remote:',remote_path
        print 'overwrite:',overwrite
        raw_input('continue?')
        if files.exists(remote_path) and not overwrite:
            print 'remote file exists, not overwriting'
            exit(1)
        put(local_path, remote_path)

def _should_be_skipped(path, allow_missing):
    return not files.exists(path) and strtobool(allow_missing)

def _user(use_bootstrap_user):
    if bool(strtobool(use_bootstrap_user)):
        return BOOTSTRAP_USER
    else:
        return DEPLOY_USER

#
# these might need a better home
#

@task
@requires_aws_stack
def cmd(stackname, command=None):
    if command is None:
        abort("Please specify a command e.g. ./bldr cmd:%s,ls" % stackname)
    with stack_conn(stackname):
        with settings(abort_on_prompts=True):
            run(command)
        
@task
def project_list():
    for org, plist in project.org_project_map().items():
        print org
        for project_name in plist:
            print '  ', project_name
        print 

@task
@requires_project
@echo_output
def project_config(pname):
    return core_utils.remove_ordereddict(project.project_data(pname))

