import logging
from tests import base
from buildercore import lifecycle, core

logging.disable(logging.NOTSET) # re-enables logging during integration testing

LOG = logging.getLogger(__name__)

# the intent here is:
# * launch multiple ec2 instances without running highstate
# * run any logic that requires multiple ec2 nodes
# * optionally leave the nodes running while debugging happens

# TODO: this class is a copy with `test_with_instance.py` with one value tweaked
# turn into a base class perhaps?
class TestWithManyNodes(base.BaseIntegrationCase):
    @classmethod
    def setUpClass(cls):
        super(TestWithManyNodes, cls).setUpClass()

        cls.setup_stack(
            project='project-with-cluster-integration-tests',
            explicitly_start=False # see self.setUp
        )

    @classmethod
    def tearDownClass(cls):
        cls.tear_down_stack(cls)
        super(TestWithManyNodes, cls).tearDownClass()

    def setUp(self):
        lifecycle.start(self.stackname)

    def test_restart_all_started(self):
        "multiple nodes can be restarted from a running state"
        history = lifecycle.restart(self.stackname)

        # two nodes rebooting in serial, node 1 first, both running
        expected_history = [
            [(1, 'running'), (2, 'running')],
            [(1, 'stopped'), (2, 'running')],
            [(1, 'running'), (2, 'running')],

            # node2, stopped -> running
            [(1, 'running'), (2, 'stopped')],
            [(1, 'running'), (2, 'running')],
        ]
        self.assertEqual(expected_history, self._remove_transient_states(history))

    def test_restart_all_stopped(self):
        "multiple nodes can be restarted from a stopped state"
        lifecycle.stop(self.stackname)
        history = lifecycle.restart(self.stackname)

        # two nodes rebooting in serial, node 1 first, both stopped
        expected_history = [
            # node1, stopped -> running
            [(1, 'stopped'), (2, 'stopped')],
            [(1, 'running'), (2, 'stopped')],

            # node2, stopped -> running
            [(1, 'running'), (2, 'running')],
        ]
        self.assertEqual(expected_history, self._remove_transient_states(history))

    def test_restart_one_stopped(self):
        "multiple nodes can be restarted from a mixed state"
        node1 = core.find_ec2_instances(self.stackname)[0]
        node1.stop()
        node1.wait_until_stopped()
        history = lifecycle.restart(self.stackname)

        # two nodes rebooting in serial, node 1 first, node1 stopped
        expected_history = [
            # node1, stopped -> running
            [(1, 'stopped'), (2, 'running')],
            [(1, 'running'), (2, 'running')],

            # node2, running -> stopped -> running
            [(1, 'running'), (2, 'stopped')],
            [(1, 'running'), (2, 'running')]
        ]
        self.assertEqual(expected_history, self._remove_transient_states(history))

    def _remove_transient_states(self, history):
        """We may or may not observe transient states while polling: if the transition is faster than our client, the state won't be in the history. For the test to be stable, transient states have to be stripped"""
        transient_states = ['pending', 'stopping']

        def _transient_states(snapshot):
            return len([state for (node, state) in snapshot if state in transient_states]) > 0
        return [snapshot for snapshot in history if not _transient_states(snapshot)]
