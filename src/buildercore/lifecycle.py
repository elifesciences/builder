"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

from datetime import datetime
import logging
import re
from fabric.contrib import files
import fabric.exceptions as fabric_exceptions
from . import config
from .core import connect_aws_with_stack, find_ec2_instances, stack_all_ec2_nodes, current_ec2_node_id, NoPublicIps, NoRunningInstances
from .utils import call_while, ensure
from .context_handler import load_context, download_from_s3

LOG = logging.getLogger(__name__)

def start(stackname):
    "Puts all EC2 nodes of stackname into the 'started' state. Idempotent"

    # update local copy of of context from s3
    download_from_s3(stackname, refresh=True)

    states = _nodes_states(stackname)
    LOG.info("Current states: %s", states)
    _ensure_valid_states(states, {'stopped', 'pending', 'running', 'stopping'})

    stopping = _select_nodes_with_state('stopping', states)
    if stopping:
        LOG.info("Nodes are stopping: %s", stopping)
        _wait_all_in_state(stackname, 'stopped', stopping)
        states = _nodes_states(stackname)
    LOG.info("Current states: %s", states)

    to_be_started = _select_nodes_with_state('stopped', states)
    if to_be_started:
        LOG.info("Nodes to be started: %s", to_be_started)
        _connection(stackname).start_instances(to_be_started)
        _wait_all_in_state(stackname, 'running', to_be_started)

        def some_node_is_not_ready():
            try:
                stack_all_ec2_nodes(stackname, _wait_daemons, username=config.BOOTSTRAP_USER)
            except NoPublicIps as e:
                LOG.info("No public ips available yet: %s", e.message)
                return True
            except NoRunningInstances as e:
                # shouldn't be necessary because of _wait_all_in_state() we do before, but the EC2 API is not consistent
                # and sometimes selecting instances filtering for the `running` state doesn't find them
                # even if their state is `running` according to the latest API call
                LOG.info("No running instances yet: %s", e.message)
                return True
            return False
        call_while(some_node_is_not_ready, interval=2, update_msg="waiting for nodes to be networked", done_msg="all nodes have public ips")
    else:
        LOG.info("Nodes are all running")

    update_dns(stackname)

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
    nodes = find_ec2_instances(stackname, allow_empty=True)

    def _parse_datetime(value):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return {node.id: _parse_datetime(node.launch_time) for node in nodes}

def stop_if_next_hour_is_imminent(stackname, minimum_minutes=55):
    maximum_minutes = 60
    starting_times = last_start_time(stackname)
    running_times = {node_id: int((datetime.utcnow() - launch_time).total_seconds()) % (maximum_minutes * 60) for (node_id, launch_time) in starting_times.items()}
    LOG.info("Hourly fraction running times: %s", running_times)

    minimum_running_time = minimum_minutes * 60
    maximum_running_time = maximum_minutes * 60
    LOG.info("Interval to select nodes to stop: %s-%s", minimum_running_time, maximum_running_time)

    to_be_stopped = [node_id for (node_id, running_time) in running_times.items() if running_time >= minimum_running_time]
    LOG.info("Selected for stopping: %s", to_be_stopped)
    if to_be_stopped:
        _connection(stackname).stop_instances(to_be_stopped)
        _wait_all_in_state(stackname, 'stopped', to_be_stopped)


def _wait_all_in_state(stackname, state, node_ids):
    def some_node_is_still_not_compliant():
        states = _nodes_states(stackname)
        LOG.info("states of %s nodes (%s): %s", stackname, node_ids, states)
        return set(states.values()) != {state}
    # TODO: timeout argument
    call_while(some_node_is_still_not_compliant, interval=2, update_msg="waiting for states of nodes to be %s" % state, done_msg="all nodes in state %s" % state)

def _ensure_valid_states(states, valid_states):
    ensure(
        set(states.values()).issubset(valid_states),
        "The states of EC2 nodes are not supported, manual recovery is needed: %s", states
    )

def _wait_daemons():
    node_id = current_ec2_node_id()
    path = '/var/lib/cloud/instance/boot-finished'

    def is_starting_daemons():
        try:
            return not files.exists(path)
        except fabric_exceptions.NetworkError:
            LOG.debug("failed to connect to %s...", node_id)
            return True
    call_while(is_starting_daemons, interval=3, update_msg='Waiting for %s to be detected on %s...' % (path, node_id))

def update_dns(stackname):
    nodes = find_ec2_instances(stackname, allow_empty=True)
    LOG.info("Nodes found for DNS update: %s", [node.id for node in nodes])
    if len(nodes) == 0:
        raise RuntimeError("No nodes found for %s, they may be in a stopped state: (%s). They need to be `running` to have a (public, at least) ip address that can be mapped onto a DNS" % (stackname, _nodes_states(stackname)))

    if len(nodes) > 1:
        # ELB has its own DNS, EC2 nodes will autoregister
        LOG.info("Multiple nodes, EC2 nodes will autoregister to ELB, nothing to do")
        return

    context = load_context(stackname)
    LOG.info("External full hostname: %s", context['full_hostname'])
    if context['full_hostname']:
        for node in nodes:
            _update_dns_a_record(stackname, context['domain'], context['full_hostname'], node.ip_address)

    # We don't strictly need to do this, as the private ip address
    # inside a VPC should stay the same. For consistency we update all DNS
    # entries as the operation is idempotent
    LOG.info("Internal full hostname: %s", context['int_full_hostname'])
    if context['int_full_hostname']:
        for node in nodes:
            _update_dns_a_record(stackname, context['int_domain'], context['int_full_hostname'], node.private_ip_address)

def delete_dns(stackname):
    context = load_context(stackname)
    if context['full_hostname']:
        LOG.info("Deleting external full hostname: %s", context['full_hostname'])
        _delete_dns_a_record(stackname, context['domain'], context['full_hostname'])
    else:
        LOG.info("No external full hostname to delete")

    if context['int_full_hostname']:
        LOG.info("Deleting internal full hostname: %s", context['int_full_hostname'])
        _delete_dns_a_record(stackname, context['int_domain'], context['int_full_hostname'])
    else:
        LOG.info("No internal full hostname to delete")

def _update_dns_a_record(stackname, zone_name, name, value):
    route53 = connect_aws_with_stack(stackname, 'route53')
    zone = route53.get_zone(zone_name)
    if zone.get_a(name).resource_records == [value]:
        LOG.info("No need to update DNS record %s (already %s)", name, value)
    else:
        LOG.info("Updating DNS record %s to %s", name, value)
        zone.update_a(name, value)

def _delete_dns_a_record(stackname, zone_name, name):
    route53 = connect_aws_with_stack(stackname, 'route53')
    zone = route53.get_zone(zone_name)
    if zone.get_a(name):
        LOG.info("Deleting DNS record %s", name)
        zone.delete_a(name)
    else:
        LOG.info("No DNS record to delete")

def _select_nodes_with_state(interesting_state, states):
    return [instance_id for (instance_id, state) in states.items() if state == interesting_state]

def _nodes_states(stackname, node_ids=None):
    """dictionary from instance id to a string state.
    e.g. {'i-6f727961': 'stopped'}"""

    def _by_node_name(ec2_data):
        "{'lax--end2end--1': [old_terminated_ec2, current_ec2]}"
        node_index = {}
        for node in ec2_data:
            name = node.tags['Name']
            # start legacy name: pattern-library--prod -> pattern-library--prod--1
            if not re.match(".*--[0-9]+", name):
                name = name + "--1"
            # end legacy name
            node_list = node_index.get(name, [])
            node_list.append(node)
            node_index[name] = node_list
        return node_index

    def _unify_node_information(nodes):
        excluding_terminated = [node for node in nodes if node.state != 'terminated']
        ensure(len(excluding_terminated) == 1, "Nodes in %s have the same name, but a non-terminated state" % excluding_terminated)
        return excluding_terminated[0]

    ec2_data = find_ec2_instances(stackname, state=None, node_ids=node_ids)
    by_node_name = _by_node_name(ec2_data)
    print by_node_name.keys()
    unified_nodes = {name: _unify_node_information(nodes) for name, nodes in by_node_name.items()}
    return {node.id: node.state for name, node in unified_nodes.items()}

def _connection(stackname):
    return connect_aws_with_stack(stackname, 'ec2')
