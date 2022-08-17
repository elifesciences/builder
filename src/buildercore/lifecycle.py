"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

from datetime import datetime
import logging
import backoff
from .command import remote_file_exists, CommandException
import boto # route53 boto2 > route53 boto3
from . import config, core, command
from .core import boto_conn, find_ec2_instances, find_rds_instances, stack_all_ec2_nodes, current_ec2_node_id, NoPublicIps, NoRunningInstances
from .utils import call_while, ensure, lmap
from .context_handler import load_context

LOG = logging.getLogger(__name__)

class EC2Timeout(RuntimeError):
    pass

def _node_id(node):
    name = core.tags2dict(node.tags)['Name']
    default_nid = 1
    _, _, nid = core.parse_stackname(name, all_bits=True)
    nid = nid or default_nid
    return int(nid)

def start_rds_nodes(stackname):
    rds_to_be_started = _rds_nodes_states(stackname)
    LOG.info("RDS nodes to be started: %s", rds_to_be_started)

    def _start(nid):
        return _rds_connection(stackname).start_db_instance(DBInstanceIdentifier=nid)
    return lmap(_start, rds_to_be_started.keys())

def start(stackname):
    "Puts all EC2 nodes and RDS instances for given `stackname` into the 'started' state. Idempotent"

    context = load_context(stackname)

    # TODO: do the same exclusion for EC2
    ec2_states = _ec2_nodes_states(stackname)
    if context.get('rds'):
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
    ec2_to_be_checked = ec2_to_be_started + _select_nodes_with_state('running', ec2_states)
    rds_to_be_started = _select_nodes_with_state('stopped', rds_states)

    if ec2_to_be_started:
        LOG.info("EC2 nodes to be started: %s", ec2_to_be_started)
        _ec2_connection(stackname).instances.filter(InstanceIds=ec2_to_be_started).start()

    if rds_to_be_started:
        LOG.info("RDS nodes to be started: %s", rds_to_be_started)
        [_rds_connection(stackname).start_db_instance(DBInstanceIdentifier=n) for n in rds_to_be_started]

    if not ec2_to_be_started:
        LOG.info("EC2 nodes are all running")

    try:
        wait_for_ec2_steady_state(stackname, ec2_to_be_checked)
    except EC2Timeout as e:
        # a persistent login problem won't be solved by a reboot
        if "Needed to prompt for a connection or sudo password" in str(e):
            raise
        # in case of botched boot and/or inability to
        # access through SSH, try once to stop and
        # start the instances again
        LOG.info("Boot failed (instance(s) not accessible through SSH). Attempting boot one more time: %s", ec2_to_be_checked)
        _ec2_connection(stackname).instances.filter(InstanceIds=ec2_to_be_checked).stop()
        _wait_ec2_all_in_state(stackname, 'stopped', ec2_to_be_checked)
        _ec2_connection(stackname).instances.filter(InstanceIds=ec2_to_be_checked).start()
        wait_for_ec2_steady_state(stackname, ec2_to_be_checked)

    if rds_to_be_started:
        _wait_rds_all_in_state(stackname, 'available', rds_to_be_started)

    update_dns(stackname)

def wait_for_ec2_steady_state(stackname, ec2_to_be_checked):
    _wait_ec2_all_in_state(stackname, 'running', ec2_to_be_checked)
    call_while(
        lambda: _some_node_is_not_ready(stackname, instance_ids=ec2_to_be_checked),
        interval=config.AWS_POLLING_INTERVAL,
        timeout=config.BUILDER_TIMEOUT,
        update_msg="waiting for nodes to complete boot",
        done_msg="all nodes have public ips, are reachable via SSH and have completed boot",
        exception_class=EC2Timeout
    )

def _some_node_is_not_ready(stackname, **kwargs):
    try:
        ip_to_ready = stack_all_ec2_nodes(stackname, _daemons_ready, username=config.BOOTSTRAP_USER, **kwargs)
        LOG.info("_some_node_is_not_ready: %s", ip_to_ready)
        return len(ip_to_ready) == 0 or False in ip_to_ready.values()
    except NoPublicIps as e:
        LOG.info("No public ips available yet: %s", e)
        return True
    except NoRunningInstances as e:
        # shouldn't be necessary because of _wait_ec2_all_in_state() we do before, but the EC2 API is not consistent
        # and sometimes selecting instances filtering for the `running` state doesn't find them
        # even if their state is `running` according to the latest API call
        LOG.info("No running instances yet: %s", e)
        return True
    except CommandException as e:
        # login problem is a legitimate error for booting servers,
        # but also a signal the SSH private key is not allowed if it persists
        if "Needed to prompt for a connection or sudo password" in str(e):
            LOG.info("SSH access problem in _some_node_is_not_ready execution: %s", e)
            return e
        LOG.info("Generic failure of _some_node_is_not_ready execution: %s (class %s)", e, type(e))
        return True
    return False

def stop(stackname, services=None):
    "Puts all EC2 nodes of stackname into the 'stopped' state. Idempotent"
    services = services or ['ec2', 'rds']
    context = load_context(stackname)

    ec2_states = _ec2_nodes_states(stackname)
    if context.get('rds'):
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
        assert value.tzname() == 'UTC', 'datetime object returned by the EC2 API is not UTC, needs timezone conversion'
        return value.replace(tzinfo=None)
    return {node.id: _parse_datetime(node.launch_time) for node in nodes}

def _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped):
    LOG.info("Selected for stopping: EC2 %s, RDS %s", ec2_to_be_stopped, rds_to_be_stopped)
    if ec2_to_be_stopped:
        _ec2_connection(stackname).instances.filter(InstanceIds=ec2_to_be_stopped).stop()
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
    call_while(
        some_node_is_still_not_compliant,
        interval=config.AWS_POLLING_INTERVAL,
        timeout=config.BUILDER_TIMEOUT,
        update_msg=("waiting for states of %s nodes to be %s" % (node_description, state)),
        done_msg="all nodes in state %s" % state
    )

def _ensure_valid_ec2_states(states, valid_states):
    ensure(
        set(states.values()).issubset(valid_states),
        "The states of EC2 nodes are not supported, manual recovery is needed: %s" % states
    )

def _daemons_ready():
    "Assumes it is connected to an ec2 host via fabric"
    node_id = current_ec2_node_id()
    path = '/var/lib/cloud/instance/boot-finished'

    try:
        return remote_file_exists(path)
    except command.NetworkError:
        LOG.debug("failed to connect to %s...", node_id)
        return False

def update_dns(stackname):
    context = load_context(stackname)
    if not context['ec2']:
        LOG.info("No EC2 nodes expected")
        return

    def _log_backoff(event):
        LOG.warning("Backing off in waiting for running nodes on %s to map them onto a DNS entry", event['args'][0])

    @backoff.on_exception(backoff.expo, core.NoRunningInstances, on_backoff=_log_backoff, max_time=30)
    def _wait_for_running_nodes(stackname):
        return find_ec2_instances(stackname)

    nodes = _wait_for_running_nodes(stackname)
    LOG.info("Nodes found for DNS update: %s", [node.id for node in nodes])

    # TODO: switch to ['dns-external-primary'] after backward compatibility is not needed anymore
    if context['ec2'].get('dns-external-primary'):
        primary = 1
        primary_hostname = context['ext_node_hostname'] % primary
        primary_ip_address = nodes[0].public_ip_address
        LOG.info("External primary full hostname: %s", primary_hostname)
        _update_dns_a_record(context['domain'], primary_hostname, primary_ip_address)

    if context.get('elb', False) or context.get('alb', False):
        # LB has its own DNS, EC2 nodes will autoregister
        LOG.info("Multiple nodes, EC2 nodes will autoregister to ELB that has a stable hostname, nothing else to do")
        # TODO: time to implement this as there may be an old A record around...
        return

    LOG.info("External full hostname: %s", context['full_hostname'])
    if context['full_hostname']:
        for node in nodes:
            _update_dns_a_record(context['domain'], context['full_hostname'], node.public_ip_address)

def delete_dns(stackname):
    context = load_context(stackname)
    if context['full_hostname']:
        LOG.info("Deleting external full hostname: %s", context['full_hostname'])
        _delete_dns_a_record(context['domain'], context['full_hostname'])
    else:
        LOG.info("No external full hostname to delete")

    if context['int_full_hostname']:
        LOG.info("Deleting internal full hostname: %s", context['int_full_hostname'])
        _delete_dns_a_record(context['int_domain'], context['int_full_hostname'])
    else:
        LOG.info("No internal full hostname to delete")

def _update_dns_a_record(zone_name, name, value):
    # "zone_name" => "elifesciences.org"
    # "name" => "foo--journal.elifesciences.org"
    # "value" => "1.2.3.4"
    zone = _r53_connection().get_zone(zone_name)
    a_record = zone.get_a(name)
    if a_record:
        if a_record.resource_records == [value]:
            LOG.info("No need to update DNS record %s (already %s)", name, value)
        else:
            LOG.info("Updating DNS record %s to %s", name, value)
            zone.update_a(name, value)
    else:
        # lsh@2021-08-02: record doesn't exist. This case almost never happens.
        # It *did* happen when a journal instance was brought up using the `prod` config.
        # It overwrote the DNS entries for `journal--prod` and then destroyed them when it rolled back.
        # `lifecycle.update_dns` is now the recommended way to fix broken DNS.
        LOG.warning("DNS record %s does not exist!", name)
        LOG.info("Creating DNS record %s with %s", name, value)
        zone.add_a(name, value)

def _delete_dns_a_record(zone_name, name):
    zone = _r53_connection().get_zone(zone_name)
    if zone.get_a(name):
        LOG.info("Deleting DNS record %s", name)
        zone.delete_a(name)
    else:
        LOG.info("No DNS record to delete")

def _select_nodes_with_state(interesting_state, states):
    return [instance_id for (instance_id, state) in states.items() if state == interesting_state]

def _ec2_nodes_states(stackname, node_ids=None):
    """returns a dictionary of ec2 `instance-id` => state.
    for example: {'i-6f727961': 'stopped'}"""

    def _by_node_name(ec2_data):
        "{'lax--end2end--1': [old_terminated_ec2, current_ec2]}"
        node_index = {}
        for node in ec2_data:
            name = core.tags2dict(node.tags)['Name']
            # start legacy name: 'pattern-library--prod' => 'pattern-library--prod--1'
            if not core.stackname_has_node(name):
                name = name + "--1"
            # end legacy name
            node_list = node_index.get(name, [])
            node_list.append(node)
            node_index[name] = node_list
        return node_index

    def _unify_node_information(nodes, name):
        excluding_terminated = [node for node in nodes if node.state['Name'] != 'terminated']
        ensure(len(excluding_terminated) <= 1, "Multiple nodes in %s have the same name (%s), but a non-terminated state" % (excluding_terminated, name))
        if len(excluding_terminated): # > 1
            return excluding_terminated[0]
        return None

    ec2_data = find_ec2_instances(stackname, state=None, node_ids=node_ids)
    by_node_name = _by_node_name(ec2_data)
    unified_including_terminated = {name: _unify_node_information(nodes, name) for name, nodes in by_node_name.items()}
    unified_nodes = {name: node for name, node in unified_including_terminated.items() if node is not None}
    return {node.id: node.state['Name'] for name, node in unified_nodes.items()}

def _rds_nodes_states(stackname):
    return {i['DBInstanceIdentifier']: i['DBInstanceStatus'] for i in find_rds_instances(stackname)}

def _ec2_connection(stackname):
    return boto_conn(stackname, 'ec2')

def _rds_connection(stackname):
    return boto_conn(stackname, 'rds', client=True)

def _r53_connection():
    """returns a *boto2* route53 connection.
    route53 for boto3 is *very* poor and much too low-level with no 'resource' construct (yet?). It should be avoided.

    http://boto.cloudhackers.com/en/latest/ref/route53.html

    lsh@2021-08: boto3 still hasn't got it's higher level 'resource' interface yet, but
    it's 'client' interface looks more fleshed out now than it did when boto3 was first
    introduced. Consider upgrading."""
    return boto.connect_route53() # no region necessary
