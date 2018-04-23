from buildercore import bluegreen
from . import base
from mock import patch, MagicMock
from collections import OrderedDict

def try_only_once(fn, interval=5, timeout=600, update_msg="waiting ...", done_msg="done.", exception_class=None):
    if not exception_class:
        exception_class = RuntimeError
    if fn():
        raise exception_class("Reached timeout %d while %s" % (timeout, update_msg))

class Primitives(base.BaseCase):
    def setUp(self):
        patcher = patch('buildercore.bluegreen.boto_client')
        self.addCleanup(patcher.stop)
        elb_conn_factory = patcher.start()
        self.conn = MagicMock()
        elb_conn_factory.return_value = self.conn
        self.concurrency = bluegreen.BlueGreenConcurrency('us-east-1')

    def test_find_load_balancer(self):
        self.conn.describe_load_balancers.return_value = {
            'LoadBalancerDescriptions': [
                {'LoadBalancerName': 'dummy1-ElasticL-ABCDEFGHI'}
            ]
        }
        self.conn.describe_tags.return_value = {
            'TagDescriptions': [
                {
                    'LoadBalancerName': 'dummy1-ElasticL-ABCDEFGHI',
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'dummy1--test'},
                    ]
                }
            ]
        }
        name = self.concurrency.find_load_balancer('dummy1--test')
        self.assertEqual(name, 'dummy1-ElasticL-ABCDEFGHI')

    @patch('buildercore.bluegreen.call_while', side_effect=try_only_once)
    def test_wait_all_in_service_success(self, call_while):
        self.conn.describe_instance_health.return_value = {
            'InstanceStates': [
                {
                    'InstanceId': 'i-10000001',
                    'State': 'InService',
                },
                {
                    'InstanceId': 'i-10000002',
                    'State': 'InService',
                },
            ],
        }
        self.concurrency.wait_all_in_service('dummy1-ElasticL-ABCDEFGHI')

    @patch('buildercore.bluegreen.call_while', side_effect=try_only_once)
    def test_wait_all_in_service_failure(self, call_while):
        self.conn.describe_instance_health.return_value = {
            'InstanceStates': [
                {
                    'InstanceId': 'i-10000001',
                    'State': 'InService',
                },
                {
                    'InstanceId': 'i-10000002',
                    'State': 'OutOfService',
                },
            ],
        }
        self.assertRaises(
            bluegreen.SomeOutOfServiceInstances,
            self.concurrency.wait_all_in_service,
            'dummy1-ElasticL-ABCDEFGHI'
        )

    def test_divide_by_color(self):
        nodes_params = {
            'key_filename': './dummy1--test.pem',
            'nodes': {
                'i-10000001': 1,
                'i-10000002': 2,
            },
            'public_ips': {
                'i-10000001': '127.0.0.1',
                'i-10000002': '127.0.0.2',
            },
            'stackname': 'dummy1--test',
            'user': 'ubuntu'
        }
        self.assertEqual(
            self.concurrency.divide_by_color(nodes_params),
            (
                {
                    'key_filename': './dummy1--test.pem',
                    'nodes': {
                        'i-10000001': 1,
                    },
                    'public_ips': {
                        'i-10000001': '127.0.0.1',
                    },
                    'stackname': 'dummy1--test',
                    'user': 'ubuntu'
                },
                {
                    'key_filename': './dummy1--test.pem',
                    'nodes': {
                        'i-10000002': 2,
                    },
                    'public_ips': {
                        'i-10000002': '127.0.0.2',
                    },
                    'stackname': 'dummy1--test',
                    'user': 'ubuntu'
                }
            )
        )

    def test_deregister(self):
        nodes_params = {
            'nodes': OrderedDict([
                ('i-10000001', 1),
                ('i-10000002', 2),
            ]),
            # ...
        }
        self.concurrency.deregister('dummy1-ElasticL-ABCDEFGHI', nodes_params)
        self.conn.deregister_instances_from_load_balancer.assert_called_once_with(
            LoadBalancerName='dummy1-ElasticL-ABCDEFGHI',
            Instances=[{'InstanceId': 'i-10000001'}, {'InstanceId': 'i-10000002'}]
        )

    def test_register(self):
        nodes_params = {
            'nodes': OrderedDict([
                ('i-10000001', 1),
                ('i-10000002', 2),
            ]),
            # ...
        }
        self.concurrency.register('dummy1-ElasticL-ABCDEFGHI', nodes_params)
        self.conn.register_instances_with_load_balancer.assert_called_once_with(
            LoadBalancerName='dummy1-ElasticL-ABCDEFGHI',
            Instances=[{'InstanceId': 'i-10000001'}, {'InstanceId': 'i-10000002'}]
        )

    def test_wait_registered_any(self):
        nodes_params = {
            'nodes': OrderedDict([
                ('i-10000001', 1),
                ('i-10000002', 2),
            ]),
            # ...
        }
        self.conn.describe_instance_health.return_value = {
            'InstanceStates': [
                {
                    'InstanceId': 'i-10000001',
                    'State': 'InService',
                },
                {
                    'InstanceId': 'i-10000002',
                    'State': 'OutOfService',
                },
            ],
        }
        self.concurrency.wait_registered_any('dummy1-ElasticL-ABCDEFGHI', nodes_params)

    def test_wait_registered_all(self):
        nodes_params = {
            'nodes': OrderedDict([
                ('i-10000001', 1),
                ('i-10000002', 2),
            ]),
            # ...
        }
        self.conn.describe_instance_health.return_value = {
            'InstanceStates': [
                {
                    'InstanceId': 'i-10000001',
                    'State': 'InService',
                },
                {
                    'InstanceId': 'i-10000002',
                    'State': 'InService',
                },
            ],
        }
        self.concurrency.wait_registered_all('dummy1-ElasticL-ABCDEFGHI', nodes_params)

    def test_wait_deregistered_all(self):
        nodes_params = {
            'nodes': OrderedDict([
                ('i-10000001', 1),
                ('i-10000002', 2),
            ]),
            # ...
        }
        self.conn.describe_instance_health.return_value = {
            'InstanceStates': [
                {
                    'InstanceId': 'i-10000001',
                    'State': 'OutOfService',
                },
                {
                    'InstanceId': 'i-10000002',
                    'State': 'OutOfService',
                },
            ],
        }
        self.concurrency.wait_deregistered_all('dummy1-ElasticL-ABCDEFGHI', nodes_params)
