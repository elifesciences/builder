"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_aws_stack, debugtask
from buildercore import bootstrap, cloudformation
from buildercore.concurrency import concurrency_for
import buildvars

import logging

LOG = logging.getLogger(__name__)

@task
@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None, concurrency='serial'):
    buildvars.switch_revision(stackname, revision)
    bootstrap.update_stack(stackname, service_list=['ec2'], concurrency=concurrency_for(stackname, concurrency))

@debugtask
@requires_aws_stack
def load_balancer_status(stackname):
    load_balancer_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    print(load_balancer_name)
