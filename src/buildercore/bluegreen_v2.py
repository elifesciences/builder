"""Performs blue-green actions over a load-balanced stack (ElasticLoadBalancer v2).

The nodes inside a stack are divided into two groups: blue and green.
Actions are performed separately on the two groups while they are detached from the load balancer."""

import logging
from . import core, utils, cloudformation, trop

LOG = logging.getLogger(__name__)

class SomeOutOfServiceInstances(RuntimeError):
    pass

def conn(stackname):
    "returns an ELBv2 connection"
    return core.boto_conn(stackname, 'elbv2', client=True)

def find_load_balancer(stackname):
    "returns name of the ELBv2 resource in the cloudformation template Outputs"
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
    "returns a list of `TargetGroup` ARNs for given `stackname`."
    return [val for key, val in cloudformation.outputs_map(stackname).items() if key.startswith('ELBv2TargetGroup')]

def _target_group_health(stackname, target_group_arn):
    "returns a map of target data for the given `target_group_arn`, keyed by the Target's ID (ec2 ARN)"
    result = conn(stackname).describe_target_health(
        TargetGroupArn=target_group_arn
    )
    return {target['Target']['Id']: target for target in result['TargetHealthDescriptions']}

def _target_group_nodes(stackname, node_params=None):
    """returns a map of {target-group-arn: [{'Id': target}, ...], ...} for Targets in `node_params`.
    if a `Target` isn't registered with the `TargetGroup` a synthetic result is returned instead.
    if `node_params` is `None` then *all* nodes are considered."""
    node_params = node_params or core.all_node_params(stackname)
    ec2_arns = sorted(node_params['nodes'].keys()) # predictable testing
    target_groups = {}
    for target_group_arn in _target_group_arn_list(stackname):
        target_groups[target_group_arn] = [{'Id': ec2_arn} for ec2_arn in ec2_arns]
    return target_groups

def _target_groups(stackname):
    "returns a map of `{target-group-arn: [{target}, ...], ...}` for all TargetGroups attached to `stackname`"
    results = {}
    for target_group_arn, target_list in _target_group_nodes(stackname).items():
        target_health = _target_group_health(stackname, target_group_arn)
        target_results = []
        for target in target_list:
            ec2_arn = target['Id']
            # synthetic response. actual valid response structure:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/elbv2.html#ElasticLoadBalancingv2.Client.describe_target_health
            unknown_health = {
                'Target': {
                    "Id": ec2_arn,
                    "Port": "~"
                },
                "TargetHealth": {
                    'State': 'no-health-data',
                    # health data is not returned for unregistered targets, so how this valid state ever gets returned I don't know ...
                    'Reason': 'Target.NotRegistered',
                    'Description': 'synthetic response, given target not registered.'
                }
            }
            health = target_health.get(ec2_arn) or unknown_health
            target_results.append(health)
        results[target_group_arn] = target_results
    return results

def _registered(stackname, node_params):
    "returns a map of {target-arn: healthy?}"
    ec2_arns = node_params['nodes'].keys()
    result = {}
    for target_group_arn, target_list in _target_groups(stackname).items():
        for target in target_list:
            if target['Target']['Id'] not in ec2_arns:
                continue
            # key has to be complex because target is present across multiple target-groups/ports
            key = (target_group_arn, target['Target']['Id'])
            # if there is a 'Reason' key then it isn't healthy/registered.
            result[key] = 'Reason' not in target['TargetHealth']
    return result

# ---

def register(stackname, node_params):
    "register all targets in all target groups that are in node_params"
    c = conn(stackname)
    for target_group_arn, target_list in _target_group_nodes(stackname, node_params).items():
        LOG.info("registering targets: %s", target_list)
        if target_list:
            c.register_targets(TargetGroupArn=target_group_arn, Targets=target_list)

def deregister(stackname, node_params):
    "deregister all targets in all target groups"
    c = conn(stackname)
    for target_group_arn, target_list in _target_group_nodes(stackname, node_params).items():
        LOG.info("deregistering targets: %s", target_list)
        if target_list:
            c.deregister_targets(TargetGroupArn=target_group_arn, Targets=target_list)

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
        # return True in registered.values() # bluegreen v1 implementation. typo?
        return all(registered.values())

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
