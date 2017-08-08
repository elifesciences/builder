from fabric.api import task
from decorators import requires_project, requires_aws_stack # , echo_output, requires_feature
from buildercore import bootstrap
import logging

LOG = logging.getLogger(__name__)

@task
@requires_project
def launch(pname, instance_id=None):
    import cfn
    cfn.launch(pname, instance_id, 'masterless')
    # opportunity to do post-launch things here

@task
@requires_aws_stack
def update(stackname):
    # this task is just temporary while I debug
    bootstrap.update_ec2_stack(stackname, 'serial')

def destroy():
    pass
