from mock import patch, MagicMock
from . import base
from buildercore import lifecycle


class TestBuildercoreLifecycle(base.BaseCase):

    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_ignores_terminated_stacks_that_have_been_replaced_by_a_new_instance(self, find_ec2_instances):
        old = MagicMock()
        old.id = 'i-123'
        old.state = 'terminated'
        old.tags = {'Name': 'dummy1--test--1'}

        new = MagicMock()
        new.id = 'i-456'
        new.state = 'running'
        new.tags = {'Name': 'dummy1--test--1'}

        find_ec2_instances.return_value = [old, new]
        self.assertEqual({'i-456': 'running'}, lifecycle._ec2_nodes_states('dummy1--test'))

    @patch('buildercore.lifecycle._stop')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_stops_instances_when_running_for_too_many_minutes(self, find_ec2_instances, _stop):
        some = MagicMock()
        some.id = 'i-456'
        some.state = 'running'
        some.tags = {'Name': 'dummy1--test--1'}
        some.launch_time = '2000-01-01T00:00:00.000Z'

        find_ec2_instances.return_value = [some]
        lifecycle.stop_if_running_for('dummy1--test', 30)
