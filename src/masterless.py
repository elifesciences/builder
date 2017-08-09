from fabric.api import local, task, settings
from decorators import requires_project, requires_aws_stack, echo_output
from buildercore import bootstrap, config, core
import logging

LOG = logging.getLogger(__name__)

@task
@requires_project
def launch(pname, instance_id=None):
    import cfn
    with settings(forward_agent=True):
        cfn.launch(pname, instance_id, 'masterless')
        # opportunity to do post-launch things here

@task
@requires_aws_stack
def update(stackname):
    # this task is just temporary while I debug
    with settings(forward_agent=True):
        bootstrap.update_ec2_stack(stackname, 'serial')

def destroy():
    pass


@task
@requires_aws_stack
def ssh(stackname, node=None):
    "maintenance ssh. uses the pem key and the bootstrap user to login."
    import cfn
    instances = core.find_ec2_instances(stackname)
    public_ip = cfn._pick_node(instances, node).ip_address
    with settings(forward_agent=True):
        # -i identify file
        local("ssh %s@%s -i %s" % (config.BOOTSTRAP_USER, public_ip, core.stack_pem(stackname)))

#
#
#

def parse_repo(string):
    repo, rev = string.split('@')
    return {
        'repo': repo,
        'rev': rev
    }

@task
@echo_output
def set_versions(stackname, *repolist):
    bits = map(parse_repo, repolist)
    return bits
