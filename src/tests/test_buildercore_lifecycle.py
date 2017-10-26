import json
from mock import patch, MagicMock
from . import base
from buildercore import cfngen, context_handler, lifecycle


class TestBuildercoreLifecycle(base.BaseCase):

    @patch('buildercore.lifecycle._some_node_is_not_ready')
    @patch('buildercore.lifecycle._ec2_connection')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_start_a_not_running_ec2_instance(self, find_ec2_instances, find_rds_instances, ec2_connection, some_node_is_not_ready):
        find_ec2_instances.side_effect = [
            [self._ec2_instance('stopped')],
            [self._ec2_instance('running')],
            [self._ec2_instance('running')] # update_dns additional call
        ]
        some_node_is_not_ready.return_value = False

        c = MagicMock()
        c.start_instances = MagicMock()
        ec2_connection.return_value = c
        lifecycle.start('dummy1--test')

    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_start_a_not_running_rds_instance(self, find_ec2_instances, find_rds_instances):
        find_ec2_instances.return_value = []
        find_rds_instances.side_effect = [
            []
        ]

        context = cfngen.build_context('project-with-rds-only', stackname='project-with-rds-only--test')
        context_handler.write_context_locally('project-with-rds-only--test', json.dumps(context))

        lifecycle.start('project-with-rds-only--test')

    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_start_idempotence(self, find_ec2_instances, find_rds_instances):
        find_ec2_instances.return_value = [self._ec2_instance('running')]
        lifecycle.start('dummy1--test')

    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_ignores_terminated_stacks_that_have_been_replaced_by_a_new_instance(self, find_ec2_instances):
        old = self._ec2_instance('terminated', 'i-123')
        new = self._ec2_instance('running', 'i-456')

        find_ec2_instances.return_value = [old, new]
        self.assertEqual({'i-456': 'running'}, lifecycle._ec2_nodes_states('dummy1--test'))

    @patch('buildercore.lifecycle._stop')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_stops_instances_when_running_for_too_many_minutes(self, find_ec2_instances, _stop):

        find_ec2_instances.return_value = [self._ec2_instance('running', launch_time='2000-01-01T00:00:00.000Z')]
        lifecycle.stop_if_running_for('dummy1--test', 30)

    def _ec2_instance(self, state='running', id='i-456', launch_time='2017-01-01T00:00:00.000Z'):
        instance = MagicMock()
        instance.id = id
        instance.state = state
        instance.tags = {'Name': 'dummy1--test--1'}
        instance.launch_time = launch_time
        return instance

