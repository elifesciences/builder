from buildercore import bluegreen
from . import base
from mock import patch, MagicMock

class Primitives(base.BaseCase):
    @patch('buildercore.bluegreen.boto_elb_conn')
    def test_find_load_balancer(self, elb_conn):
        conn = MagicMock()
        elb_conn.return_value = conn
        conn.describe_load_balancers.return_value = {
            'LoadBalancerDescriptions': [
                { 'LoadBalancerName': 'dummy1-ElasticL-ABCDEFGHI' }
            ]
        }
        conn.describe_tags.return_value = {
            'TagDescriptions' : [
                {
                    'LoadBalancerName': 'dummy1-ElasticL-ABCDEFGHI',
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'dummy1--test'},
                    ]
                }
            ]
        }
        name = bluegreen.find_load_balancer('dummy1--test')
        self.assertEquals(name, 'dummy1-ElasticL-ABCDEFGHI')

    def test_divide_by_color(self):
        params = {
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
        self.assertEquals(
            bluegreen.divide_by_color(params),
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
