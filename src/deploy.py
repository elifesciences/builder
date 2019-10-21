"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_aws_stack, debugtask
from buildercore import bootstrap, cloudformation, context_handler
from buildercore.core import boto_client
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
    context = context_handler.load_context(stackname)
    elb_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    conn = boto_client('elb', context['aws']['region'])
    health = conn.describe_instance_health(
        LoadBalancerName=elb_name,
    )['InstanceStates']
    LOG.info("Load balancer name: %s", elb_name)
    LOG.info("Health: %s", health)
