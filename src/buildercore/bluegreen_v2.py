"""Performs blue-green actions over a load-balanced stack.

The nodes inside a stack are divided into two groups: blue and green.
Actions are performed separately on the two groups while they are detached from the load balancer.
Obviously requires a load balancer."""

import logging
from . import core, utils, cloudformation, trop

LOG = logging.getLogger(__name__)

class SomeOutOfServiceInstances(RuntimeError):
    pass

def conn(stackname):
    "returns an ELBv2 connection"
    return core.boto_conn(stackname, 'elbv2', client=True)

def find_load_balancer(stackname):
    "looks for the ELBv2 resource in the cloudformation template Outputs"
    elb_name = cloudformation.read_output(stackname, trop.ALB_TITLE)
    return elb_name

def divide_by_color(node_params):
    is_blue = lambda node: node % 2 == 1
    is_green = lambda node: node % 2 == 0

    def subset(is_subset):
        subset = node_params.copy()
        subset['nodes'] = {id: node for (id, node) in node_params['nodes'].items() if is_subset(node)}
        subset['public_ips'] = {id: ip for (id, ip) in node_params['public_ips'].items() if id in subset['nodes'].keys()}
        return subset

    return subset(is_blue), subset(is_green)

def _target_groups(stackname):
    """returns a map of `{target-group-arn: [{target}, ...], ...}`.
    target data is *complete*, including health description."""
    target_group_arn_list = [val for key, val in cloudformation.outputs_map(stackname).items() if key.startswith('ELBv2TargetGroup')]
    c = conn(stackname)
    target_groups = {} # {target-group-arn: [{target: ...}, ]}
    for target_group_arn in target_group_arn_list:
        results = c.describe_target_health(
            TargetGroupArn=target_group_arn
        )['TargetHealthDescriptions']
        target_groups[target_group_arn] = results
    return target_groups

def find_targets(stackname, node_params):
    """returns a map of {target-group-arn: [{target}, ...], ...} for targets found in `node_params`.
    target data is *partial*, with *just* the `Target` description.
    Used to pass targets to the `register_target` API in bulk."""
    ec2_arns = node_params['nodes'].keys()
    target_groups = {}
    for target_group_arn, target_group_targets in _target_groups(stackname).items():
        targets = []
        for target in target_group_targets:
            target_arn = target['Target']['Id']
            if target_arn in ec2_arns:
                targets.append(target['Target'])
        target_groups[target_group_arn] = targets
    return target_groups

def _registered(stackname, node_params):
    "returns a map of {target-arn: healthy?}"
    result = {}
    for target_group_targets in _target_groups(stackname).values():
        for target in target_group_targets:
            # key has to be complex because target is present across multiple target-groups/ports
            key = (target['Target']['Id'], target['Target']['Port'])
            # if there is a 'Reason' key, it isn't healthy/registered.
            result[key] = 'Reason' not in target['TargetHealth']
    return result

def register(stackname, node_params):
    "register all targets in all target groups that are in node_params"
    c = conn(stackname)
    for target_group_arn, target_list in find_targets(stackname, node_params).items():
        LOG.info("registering targets: %s", target_list)
        c.register_targets(TargetGroupArn=target_group_arn, Targets=target_list)

def deregister(stackname, node_params):
    "deregister all targets in all target groups"
    c = conn(stackname)
    for target_group_arn, target_list in find_targets(stackname, node_params).items():
        LOG.info("deregistering targets: %s", target_list)
        c.deregister_targets(TargetGroupArn=target_group_arn, Targets=target_list)

# see also this:
# - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/elbv2.html#waiters

def wait_registered_any(stackname, node_params):
    LOG.info("Waiting for registration of any on %s: %s")  # , elb_name, _instance_ids(node_params))

    def condition():
        registered = _registered(stackname, node_params)
        LOG.info("InService: %s", registered)
        return not any(registered.values())

    # needs to be as responsive as possible,
    # to start deregistering the green group as soon as a blue server becomes available
    utils.call_while(condition, interval=1, timeout=600)

def wait_registered_all(stackname, node_params):
    LOG.info("Waiting for registration of all on %s: %s")  # , elb_name, _instance_ids(node_params))

    def condition():
        registered = _registered(stackname, node_params)
        LOG.info("InService: %s", registered)
        return not all(registered.values())

    utils.call_while(condition, interval=5, timeout=600)

def wait_deregistered_all(stackname, node_params):
    LOG.info("Waiting for deregistration of all on %s: %s")  # , elb_name, _instance_ids(node_params))

    def condition():
        registered = _registered(stackname, node_params)
        LOG.info("InService: %s", registered)
        # wait ... that isn't right. this is 'any deregistered' rather than 'all deregistered'.
        # return True in registered.values()
        return not all(v is False for v in registered.values())

    utils.call_while(condition, interval=5, timeout=600)

def wait_all_in_service(stackname):
    "behaves similarly to `wait_registered_all`, but doesn't filter nodes, has a shorter timeout and more output."

    def some_not_in_service():
        target_status_by_arn = {}
        for target_group in _target_groups(stackname).values():
            for target in target_group:
                target_status_by_arn[target['Target']['Id']] = target['TargetHealth']['State']
        LOG.info("Instance statuses on %s: %s", stackname, target_status_by_arn)
        return [status for status in target_status_by_arn.values() if status != 'healthy']

    utils.call_while(
        some_not_in_service,
        interval=5,
        timeout=60,
        update_msg='Waiting for all instances to be in service...',
        exception_class=SomeOutOfServiceInstances
    )

def _instance_ids(node_params):
    return list(node_params['nodes'].keys())


def do(single_node_work_fn, node_params):
    """`node_params` is a dictionary:
        {'stackname': ...,
         'nodes': {
            node-id: 0,
            node-id: 1,
            ...,
         },
         'public_ips': {
            node-id: ip,
            node-id: ip,
            ...
        }
    """
    stackname = node_params['stackname']
    elb_name = find_load_balancer(stackname)

    wait_all_in_service(stackname)
    blue, green = divide_by_color(node_params)

    LOG.info("Blue phase on %s: %s", elb_name, _instance_ids(blue))
    deregister(stackname, blue)
    wait_deregistered_all(stackname, blue)
    core.parallel_work(single_node_work_fn, blue)

    # this is the window of time in which old and new servers overlap
    register(stackname, blue)
    wait_registered_any(stackname, blue)

    LOG.info("Green phase on %s: %s", stackname, _instance_ids(green))
    deregister(stackname, green)
    wait_deregistered_all(stackname, green)
    core.parallel_work(single_node_work_fn, green)
    register(stackname, green)

    wait_registered_all(stackname, node_params)
