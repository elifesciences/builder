#from .context_handler import load_context
from .core import boto_elb_conn
from .utils import ensure
from pprint import pprint

def concurrency_work(single_node_work, params):
    pprint(params)
    #context = load_context(params['stackname'])
    #pprint(context)
    #assert context['elb'], "Only ELB stacks can perform blue-green deployment"
    
    #waiter = conn.get_waiter('any_instance_in_service')
    #instances = [
    #    {'InstanceId': instance_id} for instance_id in params['nodes'].keys()
    #]
    #waiter.wait(LoadBalancerName=lb, Instances=instances)
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

def divide_by_color(params):
    is_blue = lambda node: node % 2 == 1
    is_green = lambda node: node % 2 == 0
    def subset(is_subset):
        subset = params.copy()
        subset['nodes'] = {id: node for (id, node) in params['nodes'].items() if is_subset(node)}
        subset['public_ips'] = {id: ip for (id, ip) in params['public_ips'].items() if id in subset['nodes'].keys() }
        return subset
    return subset(is_blue), subset(is_green)
