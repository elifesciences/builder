import aws
from fabric.contrib.files import exists
from fabric.contrib import files
from fabric.api import settings, sudo, task, local, run, lcd, cd
from buildercore import core, bootstrap, config, project
from decorators import debugtask, echo_output, requires_project
from buildercore.decorators import osissue
from buildercore.utils import first
import utils

@echo_output
def aws_update_many_projects(pname_list):
    minions = ' or '.join(map(lambda pname: pname + "-*", pname_list))
    region = aws.find_region()
    bootstrap.update_master(region)
    with core.stack_conn(core.find_master(region)):
        sudo("salt -C '%s' state.highstate" % minions)

@debugtask
@requires_project
def aws_update_projects(pname):
    "calls state.highstate on ALL projects matching <projectname>-*"
    return aws_update_many_projects([pname])

@debugtask
@osissue("refactor. part of the shared-all strategy")
def aws_remaster_minions():
    """when we create a new master-server, we need to:
    * tell the minions to connect to the new one.
    * accept their keys
    * give the minions an update
    """

    # this has only been used once and not updated since.
    
    region = aws.find_region()
    sl = core.all_active_stacks(region)
    minion_list = filter(lambda triple: not first(triple).startswith('master-server-'), sl)
    minion_list = map(first, minion_list) # just stack names
    master_ip = bootstrap.master(region, 'public_ip')
    for stackname in minion_list:
        print 'remaster-ing %r' % stackname
        public_ip = bootstrap.ec2_instance_data(stackname).ip_address
        with settings(user=config.BOOTSTRAP_USER, host_string=public_ip, key_filename=core.deploy_user_pem()):
            cmds = [
                "echo 'master: %s' > /etc/salt/minion" % master_ip,
                "echo 'id: %s' >> /etc/salt/minion" % stackname,
                "rm /etc/salt/pki/minion/minion_master.pub",  # destroy the old master key we have
                "service salt-minion restart",
            ]
            [sudo(cmd) for cmd in cmds]

    with settings(user=config.BOOTSTRAP_USER, host_string=master_ip, key_filename=core.deploy_user_pem()):
        cmds = [
            #'service salt-master restart',
            # accept all minion's keys (potentially dangerous without review, should just be the new master)
            #'sleep 5', # I have no idea why this works.
            'salt-key -L',
            'salt-key -Ay',
        ]
        [sudo(cmd) for cmd in cmds]

    bootstrap.update_all(region)


#@requires_stack_file
def create(stackname):

    if core.stack_is_active(stackname):
        print 'stack exists and is active, cannot create'
        return
    pdata = core.project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    #bootstrap.update_master(region)
    bootstrap.create_stack(stackname)
    bootstrap.update_environment(stackname)

    
    # this has only been used once and not updated since.
    

    public_ip = aws.describe_stack(stackname)['instance']['ip_address']
    pdata = project.project_data(stackname)
    # this has all been replaced with the generic scripts/bootstrap.sh script
    with settings(user=config.BOOTSTRAP_USER, host_string=public_ip, key_filename=core.deploy_user_pem()):
        cmds = [
            "wget -O /tmp/install_salt.sh https://bootstrap.saltstack.com",
            "sh /tmp/install_salt.sh -M -P git %s" % pdata['salt'],
            "echo 'master: 127.0.0.1' > /etc/salt/minion",
            "echo 'id: %s' >> /etc/salt/minion" % stackname,
        ]
        [sudo(cmd) for cmd in cmds]

    # create and upload payload to new master
    with lcd(config.PROJECT_PATH):
        local('tar cvzf payload.tar.gz payload/')
        local('scp -i %s payload.tar.gz %s@%s:' % (core.deploy_user_pem(), config.BOOTSTRAP_USER, public_ip))

    # unpack payload and move files to their new homes
    with settings(user=config.BOOTSTRAP_USER, host_string=public_ip, key_filename=core.deploy_user_pem()):
        cmds = [
            # upload and unpack payload
            'tar xvzf ~/payload.tar.gz',
            'mv -f ~/payload/deploy-user.pem ~/.ssh/id_rsa && chmod 400 ~/.ssh/id_rsa',
            # destroy the payload
            'rm -rf ~/payload/ ~/payload.tar.gz'
        ]
        [run(cmd) for cmd in cmds]

        sudo('mkdir -p /opt/elife && chown %s /opt/elife' % config.BOOTSTRAP_USER)

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
