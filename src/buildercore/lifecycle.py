"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

import logging
from .core import connect_aws_with_stack
from .utils import call_while, die

LOG = logging.getLogger(__name__)

def start(stackname):
    "Puts all EC2 nodes of stackname into the 'started' state. Idempotent"
    
    states = _nodes_states(stackname)
    LOG.info("Current states: %s", states)
    _ensure_valid_states(states, {'stopped', 'pending', 'running'})
    to_be_started = _select_nodes_with_state('stopped', states)
    if not to_be_started:
        LOG.info("Nodes are all running")
        return

    LOG.info("Nodes to be started: %s", to_be_started)
    _connection(stackname).start_instances(to_be_started)
    _ensure_all_in_state('running', stackname)

def stop(stackname):
    "Puts all EC2 nodes of stackname into the 'stopped' state. Idempotent"
    
    states = _nodes_states(stackname)
    LOG.info("Current states: %s", states)
    _ensure_valid_states(states, {'running', 'stopping', 'stopped'})
    to_be_stopped = _select_nodes_with_state('running', states)
    if not to_be_stopped:
        LOG.info("Nodes are all stopped")
        return

    LOG.info("Nodes to be stopped: %s", to_be_stopped)
    _connection(stackname).stop_instances(to_be_stopped)
    _ensure_all_in_state('stopped', stackname)

def _ensure_all_in_state(state, stackname):
    def some_node_is_still_not_compliant():
        return set(_nodes_states(stackname).values()) != {state}
    # TODO: timeout argument
    call_while(some_node_is_still_not_compliant, interval=2, update_msg="waiting for states of nodes to be %s" % state, done_msg="all nodes in state %s" % state)

def _ensure_valid_states(states, valid_states):
    die(
        set(states.values()).issubset(valid_states),
        "The states of EC2 nodes are not supported, manual recovery is needed: %s", states
    )

def _select_nodes_with_state(interesting_state, states):
    return [instance_id for (instance_id, state) in states.iteritems() if state == interesting_state]


def _nodes_states(stackname):
    """dictionary from instance id to a string state.
    
    e.g. {'i-6f727961': 'stopped'}"""
    return {node.id:node.state for node in _nodes(stackname)}

def _nodes(stackname):
    "returns list of ec2 instances data for a *specific* stackname"
    conn = _connection(stackname)
    return conn.get_only_instances(filters=_all_nodes_filter(stackname))

def _all_nodes_filter(stackname):
    return {
        'tag-key': ['Cluster', 'Name'],
        'tag-value': [stackname],
    }

def _connection(stackname):
    return connect_aws_with_stack(stackname, 'ec2')
