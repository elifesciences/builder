"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

from datetime import datetime
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
    _wait_all_in_state(stackname, 'running', to_be_started)

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
    _wait_all_in_state(stackname, 'stopped', to_be_stopped)

def last_start_time(stackname):
    nodes = _nodes(stackname, state='running')
    def _parse_datetime(value):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return {node.id:_parse_datetime(node.launch_time) for node in nodes}

def stop_if_next_hour_is_imminent(stackname, minimum_minutes=55):
    maximum_minutes = 60
    starting_times = last_start_time(stackname)
    running_times = {node_id:int((datetime.utcnow() - launch_time).total_seconds()) % (maximum_minutes * 60) for (node_id, launch_time) in starting_times.iteritems()}
    LOG.info("Hourly fraction running times: %s", running_times)

    minimum_running_time = minimum_minutes * 60
    maximum_running_time = maximum_minutes * 60
    LOG.info("Interval to select nodes to stop: %s-%s", minimum_running_time, maximum_running_time)

    to_be_stopped = [node_id for (node_id, running_time) in running_times.iteritems() if running_time >= minimum_running_time]
    LOG.info("Selected for stopping: %s", to_be_stopped)
    if to_be_stopped:
        _connection(stackname).stop_instances(to_be_stopped) 
        _wait_all_in_state(stackname, 'stopped', to_be_stopped)


def _wait_all_in_state(stackname, state, node_ids):
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


def _nodes_states(stackname, node_ids=None):
    """dictionary from instance id to a string state.
    
    e.g. {'i-6f727961': 'stopped'}"""
    return {node.id:node.state for node in _nodes(stackname, node_ids=node_ids)}

def _nodes(stackname, state=None, node_ids=None):
    "returns list of ec2 instances data for a *specific* stackname"
    conn = _connection(stackname)
    return conn.get_only_instances(filters=_all_nodes_filter(stackname, state=state, node_ids=node_ids))

def _all_nodes_filter(stackname, state, node_ids):
    query = {
        'tag-key': ['Cluster', 'Name'],
        'tag-value': [stackname],
    }
    if state:
        query['instance-state-name'] = [state]
    if node_ids:
        query['instance-id'] = node_ids
    return query

def _connection(stackname):
    return connect_aws_with_stack(stackname, 'ec2')
