"""Performs blue-green actions over a load-balanced stack.

The nodes inside a stack are divided into two groups: blue and green. Actions are performed separately on the two groups while they are detached from the load balancer. Obviously, requires a load balancer.

nodes_params is a data structure (dictionary) .
TODO: make nodes_params a named tuple"""
import logging
from .core import boto_elb_conn, parallel_work
from .utils import ensure, call_while
from pprint import pprint

LOG = logging.getLogger(__name__)

def concurrency_work(single_node_work, nodes_params):
    # TODO: region should come from context of nodes_params['stackname']
    # TODO: transform functions into methods of a class to pass region and/or connection in the constructor
    elb_name = find_load_balancer(nodes_params['stackname'])
    blue, green = divide_by_color(nodes_params)

    LOG.info("Blue phase on %s: %s", elb_name, _instance_ids(blue))
    deregister(elb_name, blue)
    wait_deregistered_all(elb_name, blue)
    parallel_work(single_node_work, blue)

    # this is the window of time in which old and new servers overlap
    register(elb_name, blue)
    wait_registered_any(elb_name, blue)

    LOG.info("Green phase on %s: %s", elb_name, _instance_ids(blue))
    deregister(elb_name, green)
    wait_deregistered_all(elb_name, green)
    parallel_work(single_node_work, green)
    register(elb_name, green)

    wait_registered_all(elb_name, nodes_params)

def find_load_balancer(stackname):
    conn = boto_elb_conn('us-east-1')
    names = [lb['LoadBalancerName'] for lb in conn.describe_load_balancers()['LoadBalancerDescriptions']]
    ensure(len(names) >= 1, "No load balancers found")
    tags = conn.describe_tags(LoadBalancerNames=names)['TagDescriptions']
    balancers = [lb['LoadBalancerName'] for lb in tags if {'Key':'Cluster', 'Value': stackname} in lb['Tags']]
    ensure(len(balancers) == 1, "Expected to find exactly 1 load balancer, but found %s", balancers)
    return balancers[0]

def divide_by_color(nodes_params):
    is_blue = lambda node: node % 2 == 1
    is_green = lambda node: node % 2 == 0
    def subset(is_subset):
        subset = nodes_params.copy()
        subset['nodes'] = {id: node for (id, node) in nodes_params['nodes'].items() if is_subset(node)}
        subset['public_ips'] = {id: ip for (id, ip) in nodes_params['public_ips'].items() if id in subset['nodes'].keys() }
        return subset
    return subset(is_blue), subset(is_green)

def register(elb_name, nodes_params):
    LOG.info("Registering on %s: %s", elb_name, _instance_ids(nodes_params))
    conn = boto_elb_conn('us-east-1')
    conn.register_instances_with_load_balancer(
        LoadBalancerName=elb_name,
        Instances=_instances(nodes_params),
    )

def deregister(elb_name, nodes_params):
    LOG.info("Deregistering on %s: %s", elb_name, _instance_ids(nodes_params))
    conn = boto_elb_conn('us-east-1')
    conn.deregister_instances_from_load_balancer(
        LoadBalancerName=elb_name,
        Instances=_instances(nodes_params),
    )

def wait_registered_any(elb_name, nodes_params):
    LOG.info("Waiting for registration of any on %s: %s", elb_name, _instance_ids(nodes_params))
    conn = boto_elb_conn('us-east-1')
    waiter = conn.get_waiter('any_instance_in_service')
    waiter.wait(LoadBalancerName=elb_name, Instances=_instances(nodes_params))

def wait_registered_all(elb_name, nodes_params):
    LOG.info("Waiting for registration of all on %s: %s", elb_name, _instance_ids(nodes_params))
    conn = boto_elb_conn('us-east-1')
    waiter = conn.get_waiter('instance_in_service')
    waiter.wait(LoadBalancerName=elb_name, Instances=_instances(nodes_params))

def wait_deregistered_all(elb_name, nodes_params):
    LOG.info("Waiting for deregistration of all on %s: %s", elb_name, _instance_ids(nodes_params))
    instance_ids = nodes_params['nodes'].keys()
    def condition():
        conn = boto_elb_conn('us-east-1')
        health = conn.describe_instance_health(
            LoadBalancerName=elb_name,
            Instances=_instances(nodes_params)
        )['InstanceStates']
        registered = _registered(health)
        LOG.info("InService: %s", registered)
        return True in registered.values()

    call_while(condition)

def _registered(health):
    return {result['InstanceId']:result['State']=='InService' for result in health}

def _instances(nodes_params):
    return [{'InstanceId': instance_id} for instance_id in _instance_ids(nodes_params)]

def _instance_ids(nodes_params):
    return nodes_params['nodes'].keys()

