"""module for stopping and starting stacks but keeping their state, hence without destroying them.

The primary reason for doing this is to save on costs."""

import logging
import re

import backoff

from . import command, config, core, utils
from .command import (
    CommandError,
    NetworkAuthenticationError,
    NetworkTimeoutError,
    NetworkUnknownHostError,
)
from .context_handler import load_context
from .core import (
    NoPublicIpsError,
    NoRunningInstancesError,
    boto_conn,
    current_ec2_node_id,
    find_ec2_instances,
    find_rds_instances,
)
from .utils import call_while, ensure, first, lookup

LOG = logging.getLogger(__name__)

class EC2TimeoutError(RuntimeError):
    pass

def _ec2_connection(stackname):
    return boto_conn(stackname, 'ec2')

def _rds_connection(stackname):
    return boto_conn(stackname, 'rds', client=True)

def _select_nodes_with_state(interesting_state, states):
    return [instance_id for (instance_id, state) in states.items() if state == interesting_state]

def _rds_nodes_states(stackname):
    return {i['DBInstanceIdentifier']: i['DBInstanceStatus'] for i in find_rds_instances(stackname)}

def _ec2_nodes_states(stackname, node_ids=None):
    """returns a dictionary of ec2 `instance-id` => state.
    for example: {'i-6f727961': 'stopped'}"""

    def _by_node_name(ec2_data):
        "{'lax--end2end--1': [old_terminated_ec2, current_ec2]}"
        node_index = {}
        for node in ec2_data:
            name = core.tags2dict(node.tags)['Name']
            # TODO: shift this logic to core.parse_stackname
            # start legacy name: pattern-library--prod -> pattern-library--prod--1
            if not re.match(".*--[0-9]+", name):
                name = name + "--1"
            # end legacy name
            node_list = node_index.get(name, [])
            node_list.append(node)
            node_index[name] = node_list
        return node_index

    def _unify_node_information(nodes, name):
        excluding_terminated = [node for node in nodes if node.state['Name'] != 'terminated']
        ensure(len(excluding_terminated) <= 1, "Multiple nodes in %s have the same name (%s), but a non-terminated state" % (excluding_terminated, name))
        if len(excluding_terminated) >= 1:
            return excluding_terminated[0]
        return None

    ec2_data = find_ec2_instances(stackname, state=None, node_ids=node_ids)
    by_node_name = _by_node_name(ec2_data)
    unified_including_terminated = {name: _unify_node_information(nodes, name) for name, nodes in by_node_name.items()}
    unified_nodes = {name: node for name, node in unified_including_terminated.items() if node is not None}
    return {node.id: node.state['Name'] for name, node in unified_nodes.items()}

def _wait_all_in_state(stackname, state, node_ids, source_of_states, node_description):
    def some_node_is_still_not_compliant():
        states = source_of_states()
        # "waiting for lax--end2end EC2 nodes to be 'stopped': {'i-07244c0d59c74d49c': 'stopping'}
        LOG.info("waiting for %s %s nodes to be %r: %s", stackname, node_description, state, states)
        return set(states.values()) != {state}
    call_while(
        some_node_is_still_not_compliant,
        interval=config.AWS_POLLING_INTERVAL,
        timeout=config.BUILDER_TIMEOUT,
        # lsh@2022-09-19: replaced in favour of a more informative poll message.
        #update_msg=("waiting for states of %s nodes to be %s" % (node_description, state)),
        update_msg=None,
        done_msg="all nodes are in state '%s'" % state
    )

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

def _ensure_valid_ec2_states(states, valid_states):
    ensure(
        set(states.values()).issubset(valid_states),
        "The states of EC2 nodes are not supported, manual recovery is needed: %s" % states
    )

def _daemons_ready():
    "Assumes it is connected to an ec2 host via threadbare"
    node_id = current_ec2_node_id()
    path = '/var/lib/cloud/instance/boot-finished'

    try:
        return command.remote_file_exists(path)
    except (ConnectionError, ConnectionRefusedError, NetworkTimeoutError, NetworkUnknownHostError, NetworkAuthenticationError):
        LOG.debug("failed to connect to %s...", node_id)
        return False

def _some_node_is_not_ready(stackname, **kwargs):
    try:
        ip_to_ready = core.stack_all_ec2_nodes(stackname, _daemons_ready, username=config.BOOTSTRAP_USER, **kwargs)
        LOG.info("_some_node_is_not_ready: %s", ip_to_ready)
        return len(ip_to_ready) == 0 or False in ip_to_ready.values()
    except NoPublicIpsError as e:
        LOG.info("No public ips available yet: %s", e)
        return True
    except NoRunningInstancesError as e:
        # shouldn't be necessary because of _wait_ec2_all_in_state() we do before, but the EC2 API is not consistent
        # and sometimes selecting instances filtering for the `running` state doesn't find them
        # even if their state is `running` according to the latest API call
        LOG.info("No running instances yet: %s", e)
        return True
    except CommandError as e:
        # login problem is a legitimate error for booting servers,
        # but also a signal the SSH private key is not allowed if it persists
        if "Needed to prompt for a connection or sudo password" in str(e):
            LOG.info("SSH access problem in _some_node_is_not_ready execution: %s", e)
            return e
        LOG.info("Generic failure of _some_node_is_not_ready execution: %s (class %s)", e, type(e))
        return True
    return False

# ---

def wait_for_ec2_steady_state(stackname, ec2_to_be_checked):
    _wait_ec2_all_in_state(stackname, 'running', ec2_to_be_checked)
    call_while(
        # lsh@2023-05-22: added `num_attempts=1` after getting 60 minutes of polling:
        # - https://github.com/elifesciences/issues/issues/8314
        #lambda: _some_node_is_not_ready(stackname, instance_ids=ec2_to_be_checked, num_attempts=1),
        # lsh@2023-06-02: reverted `num_attempts=1` after `cfn.start` dies almost immediately.
        # I think I'd prefer the rare 60mins of polling over the common immediate failure.
        lambda: _some_node_is_not_ready(stackname, instance_ids=ec2_to_be_checked),
        interval=config.AWS_POLLING_INTERVAL,
        timeout=config.BUILDER_TIMEOUT,
        update_msg="waiting for nodes to complete boot",
        done_msg="all nodes have public ips, are reachable via SSH and have completed boot",
        exception_class=EC2TimeoutError
    )

def start(stackname):
    "Puts all EC2 nodes and RDS instances for given `stackname` into the 'started' state. Idempotent"

    context = load_context(stackname)

    # TODO: do the same exclusion for EC2
    ec2_states = _ec2_nodes_states(stackname)
    rds_states = _rds_nodes_states(stackname) if context.get('rds') else {}
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
    except EC2TimeoutError as e:
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

def stop(stackname, services=None):
    "Puts all EC2 nodes of stackname into the 'stopped' state. Idempotent"
    services = services or ['ec2', 'rds']
    context = load_context(stackname)

    ec2_states = _ec2_nodes_states(stackname)
    rds_states = _rds_nodes_states(stackname) if context.get('rds') else {}
    LOG.info("Current states: EC2 %s, RDS %s", ec2_states, rds_states)
    _ensure_valid_ec2_states(ec2_states, {'running', 'stopping', 'stopped'})

    ec2_to_be_stopped = []
    rds_to_be_stopped = []
    if 'ec2' in services:
        ec2_to_be_stopped = _select_nodes_with_state('running', ec2_states)
    if 'rds' in services:
        rds_to_be_stopped = _select_nodes_with_state('available', rds_states)
    _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped)

def _last_ec2_start_time(stackname):
    nodes = find_ec2_instances(stackname, allow_empty=True)

    def _parse_datetime(value):
        assert value.tzname() == 'UTC', 'datetime object returned by the EC2 API is not UTC and needs timezone conversion'
        # lsh@2023-11-07: everything should be UTC now
        #return value.replace(tzinfo=None)
        return value
    return {node.id: _parse_datetime(node.launch_time) for node in nodes}

def stop_if_running_for(stackname, minimum_minutes=55):
    starting_times = _last_ec2_start_time(stackname)
    now = utils.utcnow()
    running_times = {node_id: int((now - launch_time).total_seconds()) for (node_id, launch_time) in starting_times.items()}
    LOG.info("Total running times: %s", running_times)

    minimum_running_time = minimum_minutes * 60
    LOG.info("Interval to select nodes to stop: %s,+oo", minimum_running_time)

    ec2_to_be_stopped = [node_id for (node_id, running_time) in running_times.items() if running_time >= minimum_running_time]
    _stop(stackname, ec2_to_be_stopped, rds_to_be_stopped=[])

def _get_dns_a_record(zone_name, name):
    """fetches a DNS 'A' type record from `zone_name` with name `name`.
    Trailing periods are appended to `name` if not present.
    Returns the `zone_name`'s ID, the modified `name` and the 'A' record returned by Boto3.
    `zone_name` => "elifesciences.org"
    `name` => "foo--journal.elifesciences.org"
    """
    if not name.endswith('.'):
        name += "." # "foo--journal.elifesciences.org."
    r53 = core.boto_client('route53')
    zone_id = r53.list_hosted_zones_by_name(DNSName=zone_name)['HostedZones'][0]['Id']
    result = r53.list_resource_record_sets(HostedZoneId=zone_id, StartRecordName=name, StartRecordType="A", MaxItems="1")
    a_record_list = result['ResourceRecordSets']

    # "zero or one 'A' records expected for 'foo--journal.elifesciences.org.', found 2"
    ensure(len(a_record_list) <= 1, "zero or one 'A' records expected for %r, found %s" % (name, len(a_record_list)))

    # {'Name': 'continuumtest--lax.elifesciences.org.', 'Type': 'A', 'TTL': 60, 'ResourceRecords': [{'Value': '3.93.31.184'}]}
    a_record = first(a_record_list)

    # `list_resource_record_sets` is *sorting* records, and not selecting or even filtering to a specific record, so when
    # 'continuumtest--lax.elifesciences' doesn't exist the next record 'continuumtest--metrics.elifesciences' is returned!!
    # same behaviour for record type, so if the named record doesn't exist, the NS will be returned. crazy.

    if a_record and a_record['Name'] != name:
        a_record = None

    if a_record and a_record['Type'] != 'A':
        a_record = None

    return zone_id, name, a_record

def _update_dns_a_record(zone_name, name, value):
    """creates or updates a Route53 DNS 'A' record `name` in `zone_name` with `value`.
    `zone_name` => "elifesciences.org"
    `name` => "foo--journal.elifesciences.org"
    `value` => "1.2.3.4"
    """
    zone_id, name, a_record = _get_dns_a_record(zone_name, name)

    if a_record and lookup(a_record, 'ResourceRecords.0.Value', None) == value:
        # "DNS record 'foo--journal.elifesciences.org.' already '1.2.3.4', update skipped"
        LOG.info("DNS record %r already %r, update skipped", name, value)
        return

    if a_record:
        # "Updating DNS record 'foo--journal.elifesciences.org.' to '1.2.3.4'"
        LOG.info("Updating DNS record %r to %r", name, value)
        ttl = a_record['TTL']

    else:
        # lsh@2021-08-02: record doesn't exist. This case almost never happens.
        # It *did* happen when another journal instance was brought up using the `prod` config.
        # It overwrote the DNS entries for `journal--prod` and then destroyed them when it rolled back.
        # `lifecycle.update_dns` is now the recommended way to fix broken DNS.

        # "Creating DNS record 'foo--journal.elifesciences.org.' with '1.2.3.4'"
        LOG.info("Creating DNS record %r with %r", name, value)
        ttl = 600 # seconds, boto2 default

    core.boto_client('route53').change_resource_record_sets(**{
        "HostedZoneId": zone_id,
        "ChangeBatch": {
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": name,
                        "Type": "A",
                        "TTL": ttl,
                        "ResourceRecords": [
                            {"Value": value}
                        ]
                    }
                }
            ]
        }
    })

def update_dns(stackname):
    context = load_context(stackname)
    if not context['ec2']:
        LOG.info("No EC2 nodes expected")
        return

    def _log_backoff(event):
        LOG.warning("Backing off in waiting for running nodes on %s to map them onto a DNS entry", event['args'][0])

    @backoff.on_exception(backoff.expo, core.NoRunningInstancesError, on_backoff=_log_backoff, max_time=30)
    def _wait_for_running_nodes(stackname):
        return find_ec2_instances(stackname)

    nodes = _wait_for_running_nodes(stackname)
    LOG.info("Nodes found for DNS update: %s", [node.id for node in nodes])

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

def _delete_dns_a_record(zone_name, name):
    """deletes a Route53 DNS 'A' record `name` in hosted zone `zone_name`.
    `zone_name` => "elifesciences.org"
    `name` => "foo--journal.elifesciences.org"
    """
    zone_id, name, a_record = _get_dns_a_record(zone_name, name)

    if not a_record:
        LOG.info("No DNS record to delete")
        return

    # "expecting 1 resource record, found: [{'Value': '4.3.2.1'}, {'Value': '1.2.3.4'}]"
    ensure(len(a_record['ResourceRecords']) == 1, "expecting 1 resource record, found: %s" % a_record['ResourceRecords'])

    # "Deleting DNS record 'foo--journal.elifesciences.org'
    LOG.info("Deleting DNS record %r", name)
    core.boto_client('route53').change_resource_record_sets(**{
        "HostedZoneId": zone_id,
        "ChangeBatch": {
            "Changes": [
                {
                    "Action": "DELETE",
                    "ResourceRecordSet": {
                        "Name": name,
                        "Type": "A",
                        "TTL": a_record['TTL'],
                        "ResourceRecords": [
                            {"Value": a_record['ResourceRecords'][0]['Value']}
                        ]
                    }
                }
            ]
        }
    })

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
