"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

from datetime import datetime
import logging
import re
from fabric.contrib import files
import fabric.exceptions as fabric_exceptions
from . import config
from .core import connect_aws_with_stack, find_ec2_instances, find_rds_instances, stack_all_ec2_nodes, current_ec2_node_id, NoPublicIps, NoRunningInstances
from .utils import call_while, ensure
from .context_handler import load_context, download_from_s3

LOG = logging.getLogger(__name__)

def start(stackname):
    "Puts all EC2 nodes of stackname into the 'started' state. Idempotent"

    # update local copy of context from s3
    download_from_s3(stackname, refresh=True)
    context = load_context(stackname)

    # TODO: do the same exclusion for EC2
    ec2_states = _ec2_nodes_states(stackname)
    if context['project']['aws'].get('rds'):
        rds_states = _rds_nodes_states(stackname)
    else:
        rds_states = {}
    LOG.info("Current states: EC2 %s, RDS %s", ec2_states, rds_states)
    _ensure_valid_ec2_states(ec2_states, {'stopped', 'pending', 'running', 'stopping'})

    stopping = _select_nodes_with_state('stopping', ec2_states)
    # TODO: sanity check on not stopping on RDS too
    if stopping:
        LOG.info("EC2 nodes are stopping: %s", stopping)
        _wait_ec2_all_in_state(stackname, 'stopped', stopping)
        ec2_states = _ec2_nodes_states(stackname)
        LOG.info("Current states: EC2 %s, RDS %s", ec2_states, rds_states)

    ec2_to_be_started = _select_nodes_with_state('stopped', ec2_states)
    rds_to_be_started = _select_nodes_with_state('stopped', rds_states)
    if ec2_to_be_started:
        LOG.info("EC2 nodes to be started: %s", ec2_to_be_started)
        _ec2_connection(stackname).start_instances(ec2_to_be_started)
    if rds_to_be_started:
        LOG.info("RDS nodes to be started: %s", rds_to_be_started)
        [_rds_connection(stackname).start_db_instance(DBInstanceIdentifier=n) for n in rds_to_be_started]

    if ec2_to_be_started:
        _wait_ec2_all_in_state(stackname, 'running', ec2_to_be_started)
        call_while(
            lambda: _some_node_is_not_ready(stackname),
            interval=2,
            update_msg="waiting for nodes to be networked",
            done_msg="all nodes have public ips"
        )
    else:
        LOG.info("EC2 nodes are all running")

    if rds_to_be_started:
        _wait_rds_all_in_state(stackname, 'available', rds_to_be_started)

    update_dns(stackname)

def _some_node_is_not_ready(stackname):
    try:
        stack_all_ec2_nodes(stackname, _wait_daemons, username=config.BOOTSTRAP_USER)
    except NoPublicIps as e:
        LOG.info("No public ips available yet: %s", e)
        return True
    except NoRunningInstances as e:
        # shouldn't be necessary because of _wait_ec2_all_in_state() we do before, but the EC2 API is not consistent
        # and sometimes selecting instances filtering for the `running` state doesn't find them
        # even if their state is `running` according to the latest API call
        LOG.info("No running instances yet: %s", e)
        return True
    return False

def stop(stackname, services=None):
    "Puts all EC2 nodes of stackname into the 'stopped' state. Idempotent"
    if not services:
        services = ['ec2', 'rds']
    context = load_context(stackname)

    ec2_states = _ec2_nodes_states(stackname)
    if context['project']['aws'].get('rds'):
        rds_states = _rds_nodes_states(stackname)
    else:
        rds_states = {}
    LOG.info("Current states: EC2 %s, RDS %s", ec2_states, rds_states)
    _ensure_valid_ec2_states(ec2_states, {'running', 'stopping', 'stopped'})

    ec2_to_be_stopped = []
    rds_to_be_stopped = []
    if 'ec2' in services:
        ec2_to_be_stopped = _select_nodes_with_state('running', ec2_states)
    if 'rds' in services:
        rds_to_be_stopped = _select_nodes_with_state('available', rds_states)
    _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped)

def stop_if_running_for(stackname, minimum_minutes=55):
    starting_times = _last_ec2_start_time(stackname)
    running_times = {node_id: int((datetime.utcnow() - launch_time).total_seconds()) for (node_id, launch_time) in starting_times.items()}
    LOG.info("Total running times: %s", running_times)

    minimum_running_time = minimum_minutes * 60
    LOG.info("Interval to select nodes to stop: %s,+oo", minimum_running_time)

    ec2_to_be_stopped = [node_id for (node_id, running_time) in running_times.items() if running_time >= minimum_running_time]
    _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped=[])

def _last_ec2_start_time(stackname):
    nodes = find_ec2_instances(stackname, allow_empty=True)

    def _parse_datetime(value):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return {node.id: _parse_datetime(node.launch_time) for node in nodes}

def _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped):
    LOG.info("Selected for stopping: EC2 %s, RDS %s", ec2_to_be_stopped, rds_to_be_stopped)
    if ec2_to_be_stopped:
        _ec2_connection(stackname).stop_instances(ec2_to_be_stopped)
    if rds_to_be_stopped:
        [_rds_connection(stackname).stop_db_instance(DBInstanceIdentifier=n) for n in rds_to_be_stopped]

    if ec2_to_be_stopped:
        _wait_ec2_all_in_state(stackname, 'stopped', ec2_to_be_stopped)
    if rds_to_be_stopped:
        _wait_rds_all_in_state(stackname, 'stopped', rds_to_be_stopped)

def _wait_ec2_all_in_state(stackname, state, node_ids):
    return _wait_all_in_state(
        stackname,
        state,
        node_ids,
        lambda: _ec2_nodes_states(stackname),
        'EC2'
    )

def _wait_rds_all_in_state(stackname, state, node_ids):
    return _wait_all_in_state(
        stackname,
        state,
        node_ids,
        lambda: _rds_nodes_states(stackname),
        'RDS'
    )

def _wait_all_in_state(stackname, state, node_ids, source_of_states, node_description):
    def some_node_is_still_not_compliant():
        states = source_of_states()
        LOG.info("states of %s %s nodes (%s): %s", stackname, node_description, node_ids, states)
        return set(states.values()) != {state}
    # TODO: timeout argument
    call_while(
        some_node_is_still_not_compliant,
        interval=2,
        update_msg=("waiting for states of %s nodes to be %s" % (node_description, state)),
        done_msg="all nodes in state %s" % state
    )

def _ensure_valid_ec2_states(states, valid_states):
    ensure(
        set(states.values()).issubset(valid_states),
        "The states of EC2 nodes are not supported, manual recovery is needed: %s" % states
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
    context = load_context(stackname)
    if not context['ec2']:
        LOG.info("No EC2 nodes expected")
        return

    nodes = find_ec2_instances(stackname, allow_empty=True)
    LOG.info("Nodes found for DNS update: %s", [node.id for node in nodes])

    if len(nodes) == 0:
        raise RuntimeError("No nodes found for %s, they may be in a stopped state: (%s). They need to be `running` to have a (public, at least) ip address that can be mapped onto a DNS" % (stackname, _ec2_nodes_states(stackname)))

    if context.get('elb', False):
        # ELB has its own DNS, EC2 nodes will autoregister
        LOG.info("Multiple nodes, EC2 nodes will autoregister to ELB, nothing to do")
        # TODO: time to implement this as there may be an old A record around...
        return

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

def _ec2_nodes_states(stackname, node_ids=None):
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

    def _unify_node_information(nodes, name):
        excluding_terminated = [node for node in nodes if node.state != 'terminated']
        ensure(len(excluding_terminated) <= 1, "Multiple nodes in %s have the same name (%s), but a non-terminated state" % (excluding_terminated, name))
        if len(excluding_terminated):
            return excluding_terminated[0]
        return None

    ec2_data = find_ec2_instances(stackname, state=None, node_ids=node_ids)
    by_node_name = _by_node_name(ec2_data)
    unified_including_terminated = {name: _unify_node_information(nodes, name) for name, nodes in by_node_name.items()}
    unified_nodes = {name: node for name, node in unified_including_terminated.items() if node is not None}
    return {node.id: node.state for name, node in unified_nodes.items()}

def _rds_nodes_states(stackname):
    return {i['DBInstanceIdentifier']: i['DBInstanceStatus'] for i in find_rds_instances(stackname)}


def _ec2_connection(stackname):
    return connect_aws_with_stack(stackname, 'ec2')

def _rds_connection(stackname):
    return connect_aws_with_stack(stackname, 'rds', with_boto3=True)
