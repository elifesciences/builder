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
    return cloudformation.read_output(stackname, trop.ALB_TITLE)

def info(msg, stackname, node_params):
    kwargs = {'elb_name': find_load_balancer(stackname),
              'iid_list': ", ".join(node_params['nodes'].keys())}
    LOG.info(msg.format(**kwargs))

def divide_by_colour(node_params):
    is_blue = lambda node: node % 2 == 1
    is_green = lambda node: node % 2 == 0

    def subset(is_subset):
        subset = node_params.copy()
        subset['nodes'] = {id: node for (id, node) in node_params['nodes'].items() if is_subset(node)}
        subset['public_ips'] = {id: ip for (id, ip) in node_params['public_ips'].items() if id in subset['nodes'].keys()}
        return subset

    return subset(is_blue), subset(is_green)

def _target_group_arn_list(stackname):
    "returns a list of TargetGroup ARNs"
    return [val for key, val in cloudformation.outputs_map(stackname).items() if key.startswith('ELBv2TargetGroup')]

def _target_group_health(stackname, target_group_arn):
    "returns a list of target data that includes their health"
    return conn(stackname).describe_target_health(
        TargetGroupArn=target_group_arn
    )['TargetHealthDescriptions']

def _target_groups(stackname):
    "returns a map of `{target-group-arn: [{target}, ...], ...}` for all TargetGroups attached to `stackname`"
    return {target_group_arn: _target_group_health(stackname, target_group_arn) for target_group_arn in _target_group_arn_list(stackname)}

def _build_targets(stackname, node_params):
    "returns a map of {target-group-arn: [{id: target}, ...], ...} for targets in `node_params`."
    ec2_arns = sorted(node_params['nodes'].keys()) # predictable testing
    target_groups = {}
    for target_group_arn in _target_group_arn_list(stackname):
        target_groups[target_group_arn] = [{'Id': ec2_arn} for ec2_arn in ec2_arns]
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

# ---

def register(stackname, node_params):
    "register all targets in all target groups that are in node_params"
    c = conn(stackname)
    for target_group_arn, target_list in _build_targets(stackname, node_params).items():
        LOG.info("registering targets: %s", target_list)
        if target_list:
            c.register_targets(TargetGroupArn=target_group_arn, Targets=target_list)

def deregister(stackname, node_params):
    "deregister all targets in all target groups"
    c = conn(stackname)
    for target_group_arn, target_list in _build_targets(stackname, node_params).items():
        LOG.info("deregistering targets: %s", target_list)
        if target_list:
            c.deregister_targets(TargetGroupArn=target_group_arn, Targets=target_list)

# see also this:
# - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/elbv2.html#waiters

def wait_registered_any(stackname, node_params):
    info("Waiting for registration of any on {elb_name}: {iid_list}", stackname, node_params)

    def condition():
        registered = _registered(stackname, node_params)
        LOG.info("InService: %s", registered)
        return not any(registered.values())

    # needs to be as responsive as possible,
    # to start deregistering the green group as soon as a blue server becomes available
    utils.call_while(condition, interval=1, timeout=600)

def wait_registered_all(stackname, node_params):
    info("Waiting for registration of all on {elb_name}: {iid_list}", stackname, node_params)

    def condition():
        registered = _registered(stackname, node_params)
        LOG.info("InService: %s", registered)
        return not all(registered.values())

    utils.call_while(condition, interval=5, timeout=600)

def wait_deregistered_all(stackname, node_params):
    info("Waiting for deregistration of all on {elb_name}: {iid_list}", stackname, node_params)

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
        LOG.info("Instance statuses on %s: %s", find_load_balancer(stackname), target_status_by_arn)
        return [status for status in target_status_by_arn.values() if status != 'healthy']

    utils.call_while(
        some_not_in_service,
        interval=5,
        timeout=60,
        update_msg='Waiting for all instances to be in service...',
        exception_class=SomeOutOfServiceInstances
    )

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

    wait_all_in_service(stackname)
    blue, green = divide_by_colour(node_params)

    info("Blue phase on {elb_name}: {iid_list}", stackname, blue)
    deregister(stackname, blue)
    wait_deregistered_all(stackname, blue)
    core.parallel_work(single_node_work_fn, blue)

    # this is the window of time in which old and new servers overlap
    register(stackname, blue)
    wait_registered_any(stackname, blue)

    info("Green phase on {elb_name}: {iid_list}", stackname, green)
    deregister(stackname, green)
    wait_deregistered_all(stackname, green)
    core.parallel_work(single_node_work_fn, green)
    register(stackname, green)

    wait_registered_all(stackname, node_params)
