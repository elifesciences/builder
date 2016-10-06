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
        self.assertEqual({'i-456': 'running'}, lifecycle._nodes_states('dummy1--test'))
