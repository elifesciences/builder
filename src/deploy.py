"""module concerns itself with tasks involving branch deployments of projects."""

from pprint import pformat
from decorators import requires_aws_stack
from buildercore import bootstrap, cloudformation, context_handler
from buildercore.bluegreen import BlueGreenConcurrency
from buildercore.core import boto_client, all_node_params
from buildercore.concurrency import concurrency_for
import buildvars

import logging

LOG = logging.getLogger(__name__)

@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None, concurrency='serial'):
    buildvars.switch_revision(stackname, revision)
    bootstrap.update_stack(stackname, service_list=['ec2'], concurrency=concurrency_for(stackname, concurrency))

@requires_aws_stack
def load_balancer_status(stackname):
    context = context_handler.load_context(stackname)
    # TODO: delegate to BlueGreenConcurrency?
    elb_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    conn = boto_client('elb', context['aws']['region'])
    health = conn.describe_instance_health(
        LoadBalancerName=elb_name,
    )['InstanceStates']
    LOG.info("Load balancer name: %s", elb_name)
    LOG.info("Health: %s", pformat(health))

@requires_aws_stack
def load_balancer_register_all(stackname):
    context = context_handler.load_context(stackname)
    elb_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    LOG.info("Load balancer name: %s", elb_name)
    concurrency = BlueGreenConcurrency(context['aws']['region'])
    node_params = all_node_params(stackname)
    LOG.info("Register all: %s", pformat(node_params))
    concurrency.register(elb_name, node_params)
    concurrency.wait_registered_all(elb_name, node_params)
