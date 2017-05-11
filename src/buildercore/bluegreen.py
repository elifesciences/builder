#from .context_handler import load_context
import logging
from .core import boto_elb_conn
from .utils import ensure, call_while
from pprint import pprint

LOG = logging.getLogger(__name__)

def concurrency_work(single_node_work, nodes_params):
    pprint(nodes_params)
    #context = load_context(nodes_params['stackname'])
    elb_name = find_load_balancer(nodes_params['stackname'])
    
    wait_registered_all(elb_name, nodes_params)
    wait_deregistered_all(elb_name, nodes_params)
    #health = conn.describe_instance_health(LoadBalancerName=lb, Instances=instances)['InstanceStates']
    #pprint(health)
    # 1. separate blue from green
    # 2. deregister blue
    # 2.1 wait, yes because of connection draining
    # 3. perform single_node_work in parallel on blue
    # 4. register blue
    # 4.1 wait, yes, with waiter any_instance_in_service
    # 5. deregister green
    # 5.1 wait, yes because of connection draining
    # 6. perform single_node_work in parallel on green
    # 7. register green
    # 7.1 wait, yes, with all_instances_in_service

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
    conn = boto_elb_conn('us-east-1')
    conn.register_instances_from_load_balancer(
        LoadBalancerName=elb_name,
        Instances=_instances(nodes_params),
    )

def deregister(elb_name, nodes_params):
    conn = boto_elb_conn('us-east-1')
    instances = [
        {'InstanceId': instance_id} for instance_id in nodes_params['nodes'].keys()
    ]
    conn.deregister_instances_from_load_balancer(
        LoadBalancerName=elb_name,
        Instances=_instances(nodes_params),
    )

def wait_registered_any(elb_name, nodes_params):
    conn = boto_elb_conn('us-east-1')
    waiter = conn.get_waiter('any_instance_in_service')
    waiter.wait(LoadBalancerName=elb_name, Instances=_instances(nodes_params))

def wait_registered_all(elb_name, nodes_params):
    conn = boto_elb_conn('us-east-1')
    waiter = conn.get_waiter('instance_in_service')
    waiter.wait(LoadBalancerName=elb_name, Instances=_instances(nodes_params))

def wait_deregistered_all(elb_name, nodes_params):
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
    return [{'InstanceId': instance_id} for instance_id in nodes_params['nodes'].keys()]
