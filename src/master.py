"""Tasks we perform on the master server. 

See `askmaster.py` for tasks that are run on minions."""

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
        with settings(user=config.BOOTSTRAP_USER, host_string=public_ip, key_filename=core.stack_pem(stackname)):
            cmds = [
                "echo 'master: %s' > /etc/salt/minion" % master_ip,
                "echo 'id: %s' >> /etc/salt/minion" % stackname,
                "rm /etc/salt/pki/minion/minion_master.pub",  # destroy the old master key we have
                "service salt-minion restart",
            ]
            [sudo(cmd) for cmd in cmds]

    with settings(user=config.BOOTSTRAP_USER, host_string=master_ip, key_filename=core.stack_pem(stackname)):
        cmds = [
            #'service salt-master restart',
            # accept all minion's keys (potentially dangerous without review, should just be the new master)
            #'sleep 5', # I have no idea why this works.
            'salt-key -L',
            'salt-key -Ay',
        ]
        [sudo(cmd) for cmd in cmds]

    bootstrap.update_all(region)
