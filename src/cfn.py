from fabric.api import task, local, cd, lcd, settings, run, sudo, put
from fabric.contrib.files import exists
from fabfile import PROJECT_DIR
from fabric.contrib import files
from fabric.contrib.console import confirm
import aws
import utils
from decorators import requires_project, requires_aws_stack, echo_output, deffile, setdefault, admintask
import os
from os.path import join
from functools import wraps
from aws import deploy_user_pem, stack_conn

from slugify import slugify

from buildercore import config, core, cfngen, utils as core_utils, bootstrap, bakery
from buildercore.utils import first
from buildercore.config import ROOT_USER, DEPLOY_USER, BOOTSTRAP_USER
from buildercore.sync import sync_stack, sync_stacks_down

import logging

LOG = logging.getLogger(__name__)

def clear_cache():
    utils.CACHE = {}

#
# utils, decorators
#

@admintask
@echo_output
def stack_list(project=None):
    "returns a list of CloudFormation files. accepts optional project name"
    stacks = sorted(core.stack_files())
    if project:
        return filter(lambda stack: stack.startswith("%s-" % project), stacks)
    return stacks

@admintask
def project_list():
    _, all_projects = core.read_projects()
    print all_projects.keys()

def requires_stack(func):
    "test that the stack exists in the STACKS dir"
    @wraps(func)
    def _wrapper(stackname=None, *args, **kwargs):
        if not stackname or stackname not in stack_list():
            stackname = utils._pick("stack", stack_list(), default_file=deffile('.stack'))
        return func(stackname, *args, **kwargs)
    return _wrapper


#
# tasks
#

@admintask
@echo_output
def aws_detailed_stack_list(project=None):
    all_stacks = dict([(i.stack_name, i.__dict__) for i in core.raw_aws_stacks()])
    if project:
        return {k: v for k, v in all_stacks.items() if k.startswith("%s-" % project)}
    return all_stacks

@requires_stack
def aws_stack_exists(stackname):
    "we may know about the stack on disk, but it might not have been pushed to aws yet..."
    return stackname in core.all_aws_stack_names()

@task
@echo_output
@requires_stack # @requires_inactive_stack
def delete_stack_file(stackname):
    logging.getLogger('boto').setLevel(logging.CRITICAL)
    files_removed = bootstrap.delete_stack_file
    return files_removed

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

@echo_output
def aws_update_many_projects(pname_list):
    minions = ' or '.join(map(lambda pname: pname + "-*", pname_list))
    bootstrap.update_master()
    with stack_conn(core.find_master()):
        sudo("salt -C '%s' state.highstate" % minions)

@task
@requires_project
def aws_update_projects(pname):
    "calls state.highstate on ALL projects matching <projectname>-*"
    return aws_update_many_projects([pname])
    


@task
@requires_aws_stack
def aws_update_template(stackname):
    return bootstrap.update_template(stackname)


#@task
def aws_remaster_minions():
    """when we create a new master-server, we need to:
    * tell the minions to connect to the new one.
    * accept their keys
    * give the minions an update
    """
    sl = core.all_active_stacks()
    minion_list = filter(lambda triple: not first(triple).startswith('master-server-'), sl)
    minion_list = map(first, minion_list) # just stack names
    master_ip = bootstrap.master('public_ip')
    for stackname in minion_list:
        print 'remaster-ing %r' % stackname
        public_ip = bootstrap.ec2_instance_data(stackname).ip_address
        with settings(user=BOOTSTRAP_USER, host_string=public_ip, key_filename=deploy_user_pem()):
            cmds = [
                "echo 'master: %s' > /etc/salt/minion" % master_ip,
                "echo 'id: %s' >> /etc/salt/minion" % stackname,
                "rm /etc/salt/pki/minion/minion_master.pub",  # destroy the old master key we have
                "service salt-minion restart",
            ]
            [sudo(cmd) for cmd in cmds]

    with settings(user=BOOTSTRAP_USER, host_string=master_ip, key_filename=deploy_user_pem()):
        cmds = [
            #'service salt-master restart',
            # accept all minion's keys (potentially dangerous without review, should just be the new master)
            #'sleep 5', # I have no idea why this works.
            'salt-key -L',
            'salt-key -Ay',
        ]
        [sudo(cmd) for cmd in cmds]

    bootstrap.update_all()


@requires_stack
def aws_create_master(stackname):
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']
    pdata = core.project_data(stackname)
    with settings(user=BOOTSTRAP_USER, host_string=public_ip, key_filename=deploy_user_pem()):
        cmds = [
            "wget -O /tmp/install_salt.sh https://bootstrap.saltstack.com",
            "sh /tmp/install_salt.sh -M -P git %s" % pdata['salt'],
            "echo 'master: 127.0.0.1' > /etc/salt/minion",
            "echo 'id: %s' >> /etc/salt/minion" % stackname,
        ]
        [sudo(cmd) for cmd in cmds]

    # create and upload payload to new master
    with lcd(PROJECT_DIR):
        local('tar cvzf payload.tar.gz payload/')
        local('scp -i %s payload.tar.gz %s@%s:' % (deploy_user_pem(), BOOTSTRAP_USER, public_ip))

    # unpack payload and move files to their new homes
    with settings(user=BOOTSTRAP_USER, host_string=public_ip, key_filename=deploy_user_pem()):
        cmds = [
            # upload and unpack payload
            'tar xvzf ~/payload.tar.gz',
            'mv -f ~/payload/deploy-user.pem ~/.ssh/id_rsa && chmod 400 ~/.ssh/id_rsa',
            # destroy the payload
            'rm -rf ~/payload/ ~/payload.tar.gz'
        ]
        [run(cmd) for cmd in cmds]

        sudo('mkdir -p /opt/elife && chown %s /opt/elife' % BOOTSTRAP_USER)

        # clone/update repo
        if files.exists('/opt/elife/elife-builder'):
            with cd('/opt/elife/elife-builder/'):
                utils.git_purge()
                utils.git_update()
        else:
            run('git clone git@github.com:elifesciences/elife-builder.git /opt/elife/elife-builder')

        # configure Salt (already installed)
        cmds = [
            # 'mount' the salt directories in /srv
            'ln -sfT /opt/elife/elife-builder/salt/pillar /srv/pillar',
            'ln -sfT /opt/elife/elife-builder/salt/salt /srv/salt',

            # restart master and minion
            'service salt-master restart',

            # accept all minion's keys (potentially dangerous without review, should just be the new master)
            'sleep 5',  # I have no idea why this works.
            'salt-key -L',
            'salt-key -Ay',

            'service salt-minion restart',
            # provision minions (self)
            'salt-call state.highstate',        # this will tell the machine to update itself.
        ]
        with settings(warn_only=True):
            [sudo(cmd) for cmd in cmds]


@task
@requires_stack
def aws_create_stack(stackname):
    if core.stack_is_active(stackname):
        print 'stack exists and is active, cannot create'
        return
    bootstrap.update_master()
    bootstrap.create_stack(stackname)
    bootstrap.update_environment(stackname)
    return stackname

@admintask
@requires_aws_stack
def aws_update_env(stackname):
    "for debugging the bootstrap process"
    bootstrap.update_environment(stackname)

@task
@echo_output
def aws_stack_list():
    "returns a list of realized stacks. does not include deleted stacks"
    return core.all_aws_stack_names()

@task
@requires_aws_stack
def ssh(stackname, username=DEPLOY_USER):
    #public_ip = aws_describe_stack(stackname)['indexed_output']['PublicIP']
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']
    local("ssh %s@%s -i %s" % (username, public_ip, deploy_user_pem()))

@admintask
@sync_stack
def sync_stacks():
    "copies the stacks down from S3 and then uploads anything needed"
    pass

#
# local template management
#

@task
@requires_project
def create_stack(pname):
    """creates a new CloudFormation template for the given project."""
    default_instance_id = core_utils.ymd()
    more_context = {
        'instance_id': slugify(pname + "-" + utils.uin("instance id", default_instance_id)),
    }

    # prompt user for alternate configurations
    pdata = core.project_data(pname)
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
    return os.path.splitext(os.path.basename(out_fname))[0]


@admintask
@requires_project
def print_stack_template(project):
    default_instance_id = core_utils.ymd()
    more_context = dict([
        ('instance_id', slugify(project + "-" + default_instance_id)),
    ])
    context = cfngen.build_context(project, config.PROJECT_FILE, config.PILLAR_DIR, **more_context)
    print cfngen.render_template(context)

@task
@requires_project
@echo_output
def print_project_config(pname):
    return core_utils.remove_ordereddict(core.project_data(pname))
    
#
#
#

@task
@sync_stack
@requires_project
def aws_launch_instance(project):
    stackname = aws_create_stack(create_stack(project))
    if stackname:
        setdefault('.active-stack', stackname)

#
# configuration management
#

VARYING_CONFIG = {
    'elife-ci': [
        # jenkins config
        "/var/lib/jenkins/config.xml",
        "/var/lib/jenkins/users/admin/config.xml",
        "/var/lib/jenkins/hudson.tasks.Mailer.xml",  # mail config, password encrypted
        "/var/lib/jenkins/.gitconfig",

        # jenkins projects, pulled from salt pillar data
        lambda: map(lambda pname: "/var/lib/jenkins/jobs/%s/config.xml" % pname, \
                    utils.salt_pillar_data()['ci']['jenkins']['projects']),

        # jira integration
        "/var/lib/jenkins/hudson.plugins.jira.JiraProjectProperty.xml",
        "/var/lib/jenkins/jenkins-jira-plugin.xml",

        # thin backup
        "/var/lib/jenkins/thinBackup.xml",

        # GOCD config
        #"/etc/go/cruise-config.xml",
    ],

    'elife-arges': [
        "/etc/nginx/sites-available/arges.elifesciences.org",
        "/usr/share/nginx/html/editor-search.html",
    ],
}


@task
@requires_aws_stack
def gather_config(stackname, single_config=False):
    """Some configuration for applications is modified as we go along, so what we have within Salt does not accurately reflect what we want remotely. Hunting down each of these files is a huge PITA, so here is a task bundling them altogther and downloading them at once."""
    project_name = core.project_name_from_stackname(stackname)
    file_list = VARYING_CONFIG[project_name]

    # call anything callable
    callables, file_list = utils.splitfilter(callable, file_list)
    map(lambda c: file_list.extend(c() or []), callables)

    if single_config:
        file_list = [utils._pick("config", file_list, default_file=deffile('.project-config'))]

    # map files to be downloaded to a version of their original selves
    def mangle(fname):
        return fname.lstrip('/').replace('/', '-').replace(r'\ ', '-')

    #with settings(user=DEPLOY_USER, host_string=public_ip, key_filename=deploy_user_pem()):
    with stack_conn(stackname):
        f_file_list = filter(exists, file_list)
        if len(f_file_list) != len(file_list):
            print 'WARNING: some files not found (or not accessible) and were excluded:'
            print '  ' + '\n  '.join(set(file_list) - set(f_file_list))

        # download the files
        dest_dir = join(PROJECT_DIR, 'salt/salt/%s/config/' % project_name)
        # FIXME: urrrrgh.
        map(lambda f: bootstrap.download(dest_dir, [f], as_user=ROOT_USER), zip(f_file_list, map(mangle, f_file_list)))


@task
@requires_aws_stack
def gather_a_config(stackname):
    return gather_config(stackname, single_config=True)


@task
@requires_aws_stack
def download_file(stackname, path):
    fname = os.path.basename(path)
    utils.mkdirp('downloads')
    with stack_conn(stackname):
        pair = (path, fname)  # must be a tuple!
        bootstrap.download('downloads', [pair], as_user=ROOT_USER)

@task
@requires_aws_stack
@echo_output
def upload_file(stackname, local_path, remote_path, overwrite=False):
    with stack_conn(stackname):
        if files.exists(remote_path) and not overwrite:
            print 'remote file exists, not overwriting'
            exit(1)
        put(local_path, remote_path)

#
# expiry date handling
#

def ec2_instance(iid):
    import boto3
    ec2 = boto3.resource("ec2")
    return ec2.Instance(iid)

def update_tag(iid, key, val):
    i = ec2_instance(iid)
    return i.create_tags(Tags=[{'Key': key, 'Value': val}])

def set_expiry_date(iid, dt):
    return update_tag(iid, 'Expires', dt.strftime("%Y-%m-%d"))

def project_name_from_stackname(stackname):
    x = core.project_list()
    y = zip(x, map(lambda p: stackname.startswith(p + "-"), x))
    z = filter(lambda p: p[1], y)
    return z[0][0]

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
    new_project_file = core.update_project_file(path, amiid)
    core.write_project_file(new_project_file)
    print '\n' * 4
    print 'wrote', config.PROJECT_FILE
    print 'updated project file with new ami. these changes must be merged and committed manually'
    print '\n' * 4

#
# rds tests
#

@task
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
