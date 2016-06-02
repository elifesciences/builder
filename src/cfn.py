from fabric.api import task, local, cd, lcd, settings, run, sudo, put, get
from fabric.contrib.files import exists
from fabfile import PROJECT_DIR
from fabric.contrib import files
from fabric.contrib.console import confirm
import aws, utils
from decorators import requires_project, requires_aws_stack, echo_output, deffile, setdefault, debugtask, timeit
import os
from os.path import join
from functools import wraps
from aws import deploy_user_pem, stack_conn
from slugify import slugify
import buildercore
from buildercore import config, core, cfngen, utils as core_utils, bootstrap, bakery, project
from buildercore.utils import first
from buildercore.config import ROOT_USER, DEPLOY_USER, BOOTSTRAP_USER
from buildercore.sync import sync_stack, sync_stacks_down
from buildercore.decorators import osissue, osissuefn

import logging

LOG = logging.getLogger(__name__)

@debugtask
@echo_output
def stack_files(project=None):
    "returns a list of CloudFormation TEMPLATE FILES. accepts optional project name"
    stacks = sorted(core.stack_files())
    if project:
        return filter(lambda stack: stack.startswith("%s-" % project), stacks)
    return stacks

def requires_stack_file(func):
    "test that the stack exists in the STACKS dir"
    @wraps(func)
    def _wrapper(stackname=None, *args, **kwargs):
        flist = stack_files()
        if not flist:
            print 'no stack files exist!'
            return
        if not stackname or stackname not in flist:
            stackname = utils._pick("stack", flist, default_file=deffile('.stack'))
        return func(stackname, *args, **kwargs)
    return _wrapper

#
# tasks
#

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

@debugtask
@requires_stack_file
def aws_stack_exists(stackname):
    "we may know about the stack on disk, but it might not have been pushed to aws yet..."
    pdata = core.project_data_for_stackname(stackname)
    print pdata
    region = pdata['aws']['region']
    return stackname in core.all_aws_stack_names(region)

@debugtask
@requires_stack_file # @requires_inactive_stack
def delete_stack_file(stackname):
    logging.getLogger('boto').setLevel(logging.CRITICAL)
    files_removed = bootstrap.delete_stack_file
    return files_removed

@task
@sync_stack
@requires_aws_stack
def delete_stack(stackname, confirmed):
    try:
        # we want 'confirmed' to equal the boolean True
        #pylint: disable=singleton-comparison
        if confirmed == True:
            return bootstrap.delete_stack(stackname)
    except ValueError:
        # it's possible to delete a stack and for the json stack file to be missing.
        # how? nfi. maybe legacy stuff
        LOG.exception("attempting to delete stack %r and the json template is missing", stackname)

@task
@sync_stack
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
@sync_stack
@requires_aws_stack
def aws_update_stack(stackname):
    """
    Updates the CloudFormation stack with any changes, updates the master and then updates the stack software.
    Only run update commands if salt has successfully been installed.
    Update commands require that the salt deploy user `DEPLOY_USER` exists.
    """
    return bootstrap.update_stack(stackname)

@debugtask
@requires_aws_stack
def aws_update_template(stackname):
    "updates the CloudFormation stack and then updates the environment"
    return bootstrap.update_template(stackname)



@debugtask
def create_kp():
    kp = utils.uin("keypair")
    bootstrap.create_keypair(kp)

@debugtask
def delete_kp():
    kp = utils.uin("keypair")
    bootstrap.delete_keypair(kp)
    
@task
@requires_stack_file
def aws_create_stack(stackname):
    if core.stack_is_active(stackname):
        print 'stack exists and is active, cannot create'
        return
    if not core.is_master_server_stack(stackname):
        # this just pulls down the latest changes in the
        # builder on the master server and restarts salt there.
        # if we're creating a new master, it can be safely skipped
        pdata = core.project_data_for_stackname(stackname)
        region = pdata['aws']['region']
        bootstrap.update_master(region)
    bootstrap.create_stack(stackname)
    bootstrap.update_environment(stackname)
    return stackname

@debugtask
@requires_aws_stack
def aws_update_env(stackname):
    "for debugging the bootstrap process"
    bootstrap.update_environment(stackname)

@task
@echo_output
def aws_stack_list():
    "returns a list of realized stacks. does not include deleted stacks"
    region = aws.find_region()
    return core.all_aws_stack_names(region)

@task
@requires_aws_stack
def ssh(stackname, username=DEPLOY_USER):
    #public_ip = aws_describe_stack(stackname)['indexed_output']['PublicIP']
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']
    local("ssh %s@%s -i %s" % (username, public_ip, deploy_user_pem()))

@debugtask
@sync_stack
def sync_stacks():
    "copies the stacks down from S3 and then uploads anything needed"
    pass

#
# local template management
#

@task
@requires_project
@echo_output
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

    _, out_fname = cfngen.generate_stack(pname, **more_context)

    print
    print 'CloudFormation template written to:', out_fname
    print 'use `fab cfn.aws_create_stack` next'
    print
    
    return stackname


'''
@debugtask
@requires_project
def print_stack_template(project):
    default_instance_id = core_utils.ymd()
    more_context = dict([
        ('instance_id', slugify(project + "-" + default_instance_id)),
    ])
    context = cfngen.build_context(project, config.PROJECT_FILE, config.PILLAR_DIR, **more_context)
    print cfngen.render_template(context)
'''

@task
@requires_project
@echo_output
def print_project_config(pname):
    return core_utils.remove_ordereddict(project.project_data(pname))
    
#
#
#

@task
@sync_stack
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

        stackname = aws_create_stack(stackname)
        if stackname:
            setdefault('.active-stack', stackname)
    except core.NoMasterException, e:
        LOG.warn(e.message)
        print "\n%s\ntry `./bldr master.create`'" % e.message

@task
@requires_aws_stack
def download_file(stackname, *args, **kwargs):
    with stack_conn(stackname):
        get(*args, **kwargs)

@task
@requires_aws_stack
def upload_file(stackname, local_path, remote_path, overwrite=False):
    with stack_conn(stackname):
        if files.exists(remote_path) and not overwrite:
            print 'remote file exists, not overwriting'
            exit(1)
        put(local_path, remote_path)

@task
@sync_stack
@requires_aws_stack
def create_ami(stackname):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r. Continue?" % pname
    if not confirm(msg, default=False):
        print 'doing nothing'
        return
    amiid = bakery.create_ami(stackname)
    #amiid = "ami-e9ff3682"
    print 'AWS is now creating AMI with id', amiid
    path = pname + '.aws.ami'
    # wait until ami finished creating?
    #core.update_project_file(pname + ".aws.ami", amiid)
    new_project_file = project.update_project_file(path, amiid)
    output_file = project.write_project_file(new_project_file)
    print '\n' * 4
    print 'wrote', output_file
    print 'updated project file with new ami. these changes must be merged and committed manually'
    print '\n' * 4

#
# rds tests
#

@debugtask
@requires_aws_stack
@echo_output
def aws_rds_snapshots(stackname):
    from boto import rds
    conn = rds.RDSConnection()
    instance = conn.get_all_dbinstances(instance_id=stackname)[0]
    # all snapshots order by creation time
    objdata = conn.get_all_dbsnapshots(instance_id=instance.id)
    data = sorted(map(lambda ss: ss.__dict__, objdata), key=lambda i: i['snapshot_create_time'])
    return data
