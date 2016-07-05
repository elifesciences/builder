from fabric.api import task, local, cd, lcd, settings, run, sudo, put, get, abort
from fabric.contrib.files import exists
from fabric.contrib import files
from fabric.contrib.console import confirm
import aws, utils
from decorators import requires_project, requires_aws_stack, echo_output, deffile, setdefault, debugtask, timeit
import os
from os.path import join
from functools import wraps
from slugify import slugify
import buildercore
from buildercore import config, core, cfngen, utils as core_utils, bootstrap, bakery, project
from buildercore.core import stack_conn, stack_pem
from buildercore.utils import first
from buildercore.config import ROOT_USER, DEPLOY_USER, BOOTSTRAP_USER
from buildercore.decorators import osissue, osissuefn

import logging

LOG = logging.getLogger(__name__)

@task
def project_list():
    for org, plist in project.org_project_map().items():
        print org
        for p in plist:
            print '  ',p
        print 

@debugtask
@echo_output
def aws_detailed_stack_list(project=None):
    region = aws.find_region()
    all_stacks = dict([(i.stack_name, i.__dict__) for i in core.raw_aws_stacks(region)])
    if project:
        return {k: v for k, v in all_stacks.items() if k.startswith("%s-" % project)}
    return all_stacks

@task
@requires_aws_stack
def aws_delete_stack(stackname):
    "tells aws to delete a stack. this doesn't delete the CloudFormation file from the stacks dir"
    print 'this is a BIG DEAL. you cannot recover from this.'
    print 'type the name of the stack to continue or anything else to quit'
    uin = raw_input('> ')
    if not uin or not uin.strip().lower() == stackname.lower():
        import difflib
        print 'you needed to type "%s" to continue.' % stackname
        print 'got:'
        print '\n'.join(difflib.ndiff([stackname], [uin]))
        exit(1)
    return delete_stack(stackname, confirmed=True)

@task
@requires_aws_stack
def aws_update_stack(stackname):
    """Updates the master and then updates the stack software.
    Only run update commands if salt has successfully been installed.
    Update commands require that the salt deploy user `DEPLOY_USER` exists."""
    return bootstrap.update_stack(stackname)

@task
def update_master():
    return bootstrap.update_stack(core.find_master(aws.find_region()))

@debugtask
@requires_aws_stack
def highstate(stackname):
    "a fast update with many caveats. if you have the time, prefer aws_update_stack instead"
    with stack_conn(stackname, username=BOOTSTRAP_USER):
        sudo('salt-call saltutil.refresh_pillar') # not sure if this even does anything ...
        sudo('salt-call state.highstate')
        
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
    return core.all_aws_stack_names(region)

@task
@requires_aws_stack
def ssh(stackname, username=DEPLOY_USER):
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    # -A forwarding of authentication agent connection
    local("ssh %s@%s -A" % (username, public_ip))

@task
@requires_aws_stack
def cmd(stackname, command=None):
    if command is None:
        abort("Please specify a command e.g. ./bldr cmd:%s,ls" % stackname)
    with stack_conn(stackname):
        with settings(abort_on_prompts=True):
            run(command)

@task
@requires_aws_stack
def owner_ssh(stackname):
    "maintainence ssh. uses the pem key and the bootstrap user to login."
    public_ip = core.stack_data(stackname)['instance']['ip_address']
    # -i identify file
    # -A forwarding of authentication agent connection
    local("ssh %s@%s -i %s -A" % (BOOTSTRAP_USER, public_ip, stack_pem(stackname)))

@requires_project
def create_stack(pname):
    """creates a new CloudFormation template for the given project."""
    default_instance_id, cluster_id = core_utils.ymd(), None
    inst_id = utils.uin("instance id", default_instance_id)
    stackname = core.mk_stackname(pname, inst_id, cluster_id)
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

@task
@requires_project
@echo_output
def config(pname):
    return core_utils.remove_ordereddict(project.project_data(pname))
    
@task
@requires_project
def aws_launch_instance(project):
    try:
        stackname = create_stack(project)
        pdata = core.project_data_for_stackname(stackname)

        print 'attempting to create stack:'
        print '  stackname: ' + stackname
        print '  region:    ' + pdata['aws']['region']
        print '  vpc:       ' + pdata['aws']['vpc-id']
        print '  subnet:    ' + pdata['aws']['subnet-id']
        print
        if not confirm('continue?', default=True):
            exit()

        stackname = aws_create_update_stack(stackname)

        if stackname.startswith('master-server--'):
            print
            print "`master-server` projects must create a deploy key in it's `formula-repo` project"
            print 
            print
        
        if stackname:
            setdefault('.active-stack', stackname)
    except core.NoMasterException, e:
        LOG.warn(e.message)
        print "\n%s\ntry `./bldr master.create`'" % e.message

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
        if files.exists(remote_path) and not overwrite:
            print 'remote file exists, not overwriting'
            exit(1)
        put(local_path, remote_path)
