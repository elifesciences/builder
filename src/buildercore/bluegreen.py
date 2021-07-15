"""Performs blue-green actions over a load-balanced stack.

The nodes inside a stack are divided into two groups: blue and green. 
Actions are performed separately on the two groups while they are detached from the load balancer. 
Obviously requires a load balancer."""

import logging
from .core import boto_client, parallel_work
from .cloudformation import read_output
from .utils import call_while

LOG = logging.getLogger(__name__)

class BlueGreenConcurrency(object):
    def __init__(self, region):
        self.conn = boto_client('elb', region)

    def __call__(self, single_node_work, nodes_params):
        """`nodes_params` is a dictionary: 
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
        elb_name = self.find_load_balancer(nodes_params['stackname'])
        self.wait_all_in_service(elb_name)
        blue, green = self.divide_by_color(nodes_params)

        LOG.info("Blue phase on %s: %s", elb_name, self._instance_ids(blue))
        self.deregister(elb_name, blue)
        self.wait_deregistered_all(elb_name, blue)
        parallel_work(single_node_work, blue)

        # this is the window of time in which old and new servers overlap
        self.register(elb_name, blue)
        self.wait_registered_any(elb_name, blue)

        LOG.info("Green phase on %s: %s", elb_name, self._instance_ids(green))
        self.deregister(elb_name, green)
        self.wait_deregistered_all(elb_name, green)
        parallel_work(single_node_work, green)
        self.register(elb_name, green)

        self.wait_registered_all(elb_name, nodes_params)

    def find_load_balancer(self, stackname):
        elb_name = read_output(stackname, 'ElasticLoadBalancer')
        LOG.info("Found load balancer: %s", elb_name)
        return elb_name

    def divide_by_color(self, nodes_params):
        is_blue = lambda node: node % 2 == 1
        is_green = lambda node: node % 2 == 0

        def subset(is_subset):
            subset = nodes_params.copy()
            subset['nodes'] = {id: node for (id, node) in nodes_params['nodes'].items() if is_subset(node)}
            subset['public_ips'] = {id: ip for (id, ip) in nodes_params['public_ips'].items() if id in subset['nodes'].keys()}
            return subset
        return subset(is_blue), subset(is_green)

    def wait_all_in_service(self, elb_name):
        def condition():
            health = self.conn.describe_instance_health(
                LoadBalancerName=elb_name,
            )['InstanceStates']
            service_status_by_id = {result['InstanceId']: result['State'] for result in health}
            LOG.info("Instance statuses on %s: %s", elb_name, service_status_by_id)
            return [bad_status for bad_status in service_status_by_id.values() if bad_status != 'InService']

        call_while(
            condition,
            interval=5,
            timeout=60,
            update_msg='Waiting for all instances to be in service...',
            exception_class=SomeOutOfServiceInstances
        )

    def register(self, elb_name, nodes_params):
        LOG.info("Registering on %s: %s", elb_name, self._instance_ids(nodes_params))
        self.conn.register_instances_with_load_balancer(
            LoadBalancerName=elb_name,
            Instances=self._instances(nodes_params),
        )

    def deregister(self, elb_name, nodes_params):
        LOG.info("Deregistering on %s: %s", elb_name, self._instance_ids(nodes_params))
        self.conn.deregister_instances_from_load_balancer(
            LoadBalancerName=elb_name,
            Instances=self._instances(nodes_params),
        )

    def wait_registered_any(self, elb_name, nodes_params):
        LOG.info("Waiting for registration of any on %s: %s", elb_name, self._instance_ids(nodes_params))

        def condition():
            registered = self._registered(elb_name, nodes_params)
            LOG.info("InService: %s", registered)
            return True not in registered.values()

        # needs to be as responsive as possible,
        # to start deregistering the green group as soon as a blue server becomes available
        call_while(condition, interval=1, timeout=600)

    def wait_registered_all(self, elb_name, nodes_params):
        LOG.info("Waiting for registration of all on %s: %s", elb_name, self._instance_ids(nodes_params))

        def condition():
            registered = self._registered(elb_name, nodes_params)
            LOG.info("InService: %s", registered)
            return False in registered.values()

        call_while(condition, interval=5, timeout=600)

    def wait_deregistered_all(self, elb_name, nodes_params):
        LOG.info("Waiting for deregistration of all on %s: %s", elb_name, self._instance_ids(nodes_params))

        def condition():
            registered = self._registered(elb_name, nodes_params)
            LOG.info("InService: %s", registered)
            return True in registered.values()

        call_while(condition, interval=5, timeout=600)

    def _registered(self, elb_name, nodes_params):
        health = self.conn.describe_instance_health(
            LoadBalancerName=elb_name,
            Instances=self._instances(nodes_params)
        )['InstanceStates']
        return {result['InstanceId']: result['State'] == 'InService' for result in health}

    def _instances(self, nodes_params):
        return [{'InstanceId': instance_id} for instance_id in self._instance_ids(nodes_params)]

    def _instance_ids(self, nodes_params):
        return list(nodes_params['nodes'].keys())

class SomeOutOfServiceInstances(RuntimeError):
    pass
