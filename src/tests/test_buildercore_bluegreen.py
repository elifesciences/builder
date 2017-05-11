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
