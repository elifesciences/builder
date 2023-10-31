"""module concerns itself with tasks involving branch deployments of projects."""

import logging
from pprint import pformat

import buildvars
from buildercore import (
    bluegreen,
    bluegreen_v2,
    bootstrap,
    cloudformation,
    context_handler,
    core,
    trop,
)
from buildercore.concurrency import concurrency_for
from buildercore.core import all_node_params
from decorators import requires_aws_stack, requires_aws_stack_template

LOG = logging.getLogger(__name__)

def load_balancer_status__v1(stackname):
    elb_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    conn = core.boto_conn(stackname, 'elb', client=True)
    health = conn.describe_instance_health(
        LoadBalancerName=elb_name,
    )['InstanceStates']
    LOG.info("Load balancer name: %s", elb_name)
    LOG.info("Health: %s", pformat(health))

def load_balancer_status__v2(stackname):
    conn = core.boto_conn(stackname, 'elbv2', client=True)
    health_list = []
    for target_group_arn in bluegreen_v2._target_group_arn_list(stackname):
        for health in conn.describe_target_health(
            TargetGroupArn=target_group_arn
        )['TargetHealthDescriptions']:
            port = health['Target']['Port']
            iid = health['Target']['Id']
            state = health['TargetHealth']['State']
            desc = 'Instance %r on port %r is %s' % (iid, port, state)
            if state != 'healthy':
                # 'reason' not present when state is healthy
                desc += ': %s' % health['TargetHealth']['Reason']
            health_list.append(
                {'Description': desc,
                 'InstanceId': iid,
                 'Port': port})
    LOG.info("Health: %s", pformat(health_list))

def load_balancer_register_all__v1(stackname):
    context = context_handler.load_context(stackname)
    elb_name = cloudformation.read_output(stackname, 'ElasticLoadBalancer')
    executor = bluegreen.BlueGreenConcurrency(context['aws']['region'])
    node_params = all_node_params(stackname)
    LOG.info("Register all: %s", pformat(node_params))
    executor.register(elb_name, node_params)
    executor.wait_registered_all(elb_name, node_params)

def load_balancer_register_all__v2(stackname):
    elb_name = cloudformation.read_output(stackname, trop.ALB_TITLE)
    LOG.info("Load balancer name: %s", elb_name)
    node_params = all_node_params(stackname)
    LOG.info("Register all: %s", pformat(node_params))
    bluegreen_v2.register(stackname, node_params)
    bluegreen_v2.wait_registered_all(stackname, node_params)

# --- api

# todo: what is using this? consider moving to `report.py`, it has nothing to do with deploying things
@requires_aws_stack
@requires_aws_stack_template
def load_balancer_status(stackname):
    "prints the 'health' status of ec2 instances attached to the load balancer."
    if cloudformation.template_using_elb_v1(stackname):
        load_balancer_status__v1(stackname)
    elif cloudformation.template_using_elb_v2(stackname):
        load_balancer_status__v2(stackname)
    else:
        LOG.debug("no load balancer found: %s", stackname)

@requires_aws_stack
@requires_aws_stack_template
def load_balancer_register_all(stackname):
    "Add all of a stack's ec2 nodes to it's load balancer."
    if cloudformation.template_using_elb_v1(stackname):
        load_balancer_register_all__v1(stackname)
    elif cloudformation.template_using_elb_v2(stackname):
        load_balancer_register_all__v2(stackname)
    else:
        LOG.debug("no load balancer found: %s", stackname)

@requires_aws_stack
@requires_aws_stack_template
def switch_revision_update_instance(stackname, revision=None, concurrency='serial'):
    "changes the revision of the stack's project and then calls highstate."
    buildvars.switch_revision(stackname, revision)
    # if lb present, ensure all nodes are registered.
    # otherwise the blue-green concurrency may timeout waiting for all nodes to be in service:
    # - https://github.com/elifesciences/issues/issues/8057
    load_balancer_register_all(stackname)
    bootstrap.update_stack(stackname, service_list=['ec2'], concurrency=concurrency_for(stackname, concurrency))
