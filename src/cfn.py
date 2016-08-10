from fabric.api import task, local, cd, settings, run, sudo, put, get, abort
from fabric.contrib import files
from fabric.contrib.console import confirm
import aws, utils
from decorators import requires_project, requires_aws_stack, requires_steady_stack, echo_output, setdefault, debugtask
import os
from os.path import join
from distutils.util import strtobool
from buildercore import core, cfngen, utils as core_utils, bootstrap, project, checks
from buildercore.core import stack_conn, stack_pem
from buildercore.config import DEPLOY_USER, BOOTSTRAP_USER

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
def create_stack(pname):
    """creates a new CloudFormation template for the given project."""
    default_instance_id = core_utils.ymd()
    inst_id = utils.uin("instance id", default_instance_id)
    stackname = core.mk_stackname(pname, inst_id)
    more_context = {'instance_id': stackname}

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

def create_update(stackname):
    if not core.stack_is_active(stackname):
        print 'stack does not exist, creating'
        bootstrap.create_stack(stackname)
    print 'updating stack'
    bootstrap.update_stack(stackname)
    return stackname

# these aliases are deprecated
@task(alias='aws_launch_instance')
@requires_project
def launch(pname):
    try:
        stackname = create_stack(pname)
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
        
        stackname = create_update(stackname)        
        if stackname:
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
def ssh(stackname, username=DEPLOY_USER, forward_agent="True"):
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    local("ssh %s@%s %s" % (username, public_ip, _ssh_flags(forward_agent)))

@task
@requires_aws_stack
def owner_ssh(stackname, forward_agent="True"):
    "maintainence ssh. uses the pem key and the bootstrap user to login."
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    # -i identity file
    local("ssh %s@%s -i %s %s" % (BOOTSTRAP_USER, public_ip, stack_pem(stackname), _ssh_flags(forward_agent)))

def _ssh_flags(forward_agent):
    # -A forwarding of authentication agent connection
    if strtobool(forward_agent):
        return "-A"
    else:
        return ""
        
@task
@requires_aws_stack
def download_file(stackname, path, destination):
    fname = os.path.basename(path)
    utils.mkdirp(destination)
    with stack_conn(stackname):
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
        for p in plist:
            print '  ',p
        print 

@task
@requires_project
@echo_output
def project_config(pname):
    return core_utils.remove_ordereddict(project.project_data(pname))
