"general logic for the `buildercore` module."

import logging
import os
import time
from collections import OrderedDict
from contextlib import contextmanager
from os.path import join

import boto3
import botocore
import botocore.config
from kids.cache import cache as cached
from slugify import slugify

from . import (  # BE SUPER CAREFUL OF CIRCULAR DEPENDENCIES
    command,
    config,
    context_handler,
    decorators,
    project,
    utils,
)
from .command import (
    CommandError,
    NetworkAuthenticationError,
    NetworkError,
    NetworkTimeoutError,
    NetworkUnknownHostError,
    env,
    settings,
)
from .utils import ensure, first, isstr, lfilter, lmap, lookup, subdict, unique

LOG = logging.getLogger(__name__)
boto3.set_stream_logger(name='botocore', level=logging.INFO)

# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudformation.html#CloudFormation.Client.describe_stacks
ALL_CFN_STATUS = [
    'CREATE_IN_PROGRESS',
    'CREATE_FAILED',
    'CREATE_COMPLETE',
    'ROLLBACK_IN_PROGRESS',
    'ROLLBACK_FAILED',
    'ROLLBACK_COMPLETE',
    'DELETE_IN_PROGRESS',
    'DELETE_FAILED',
    'DELETE_COMPLETE',
    'UPDATE_IN_PROGRESS',
    'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_COMPLETE',
    'UPDATE_FAILED',
    'UPDATE_ROLLBACK_IN_PROGRESS',
    'UPDATE_ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_ROLLBACK_COMPLETE',
    # imports not supported/used so far
    # 'REVIEW_IN_PROGRESS',
    # 'IMPORT_IN_PROGRESS',
    # 'IMPORT_COMPLETE',
    # 'IMPORT_ROLLBACK_IN_PROGRESS',
    # 'IMPORT_ROLLBACK_FAILED',
    # 'IMPORT_ROLLBACK_COMPLETE',
]

# TODO: rename 'healthy', 'active' is a bit ambiguous.
# and shouldn't 'rollback complete' be in this list?
ACTIVE_CFN_STATUS = [
    'CREATE_COMPLETE',
    'UPDATE_COMPLETE',
    'UPDATE_ROLLBACK_COMPLETE',
]

# non-transitioning 'steady states'
STEADY_CFN_STATUS = [
    'CREATE_FAILED',
    'CREATE_COMPLETE',
    'ROLLBACK_FAILED',
    'ROLLBACK_COMPLETE',
    'DELETE_FAILED',
    # 'DELETE_COMPLETE', # technically true, but we can't do anything with these.
    'UPDATE_COMPLETE',
    'UPDATE_ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_COMPLETE',
]

# just an example
# UNSTEADY_CFN_STATUS = list(set(ALL_CFN_STATUS) - set(STEADY_CFN_STATUS))

# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
ALL_EC2_STATES = [
    "pending",
    "running",
    "stopping",
    "stopped",
    "shutting-down",
    "terminated"
]

#
# sns
#

def _all_sns_subscriptions(region):
    paginator = boto_client('sns', region).get_paginator('list_subscriptions')
    return utils.shallow_flatten([page['Subscriptions'] for page in paginator.paginate()])

def all_sns_subscriptions(region, stackname=None):
    """returns all SQS subscriptions to all SNS topics.
    optionally filter subscriptions by the SQS subscriptions for given `stackname`.

    When given a stack we can fetch the names of all SQS queues and any SNS topics.
    Unfortunately there is no boto method to filter SNS subscriptions by SQS name.
    An SQS queue may also be subscribed to multiple different topics,
    as well as being subscribed to the *same* topic multiple times (somehow, de-duping
    is handled in `bootstrap.unsub_sqs`)."""

    # a subscription looks like:
    # {'Endpoint': 'arn:aws:sqs:us-east-1:512686554592:observer--substest1',
    #  'Owner':    '512686554592',
    #  'Protocol': 'sqs',
    #  'SubscriptionArn': 'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1:f44c42db-81c0-4504-b3de-51b0fb1099ff',
    #  'TopicArn': 'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1'}

    subs_list = _all_sns_subscriptions(region)
    if stackname:
        context = context_handler.load_context(stackname)
        known_sqs_name_set = set(context.get('sqs', {}))

        def fn(sub):
            return sub['Protocol'] == 'sqs' and sub['Endpoint'].split(':')[-1] in known_sqs_name_set
        subs_list = lfilter(fn, subs_list)

    # add a 'Topic' key for easier filtering downstream
    # 'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1' => 'bus-articles--substest1'
    lmap(lambda row: row.update({'Topic': row['TopicArn'].split(':')[-1]}), subs_list)
    return subs_list

#
#
#

def boto_resource(service, region=None):
    kwargs = {}
    if region:
        kwargs['region_name'] = region
    if service == 'ec2':
        # lsh@2022-07-25: set the retry mode to 'adaptive' (experimental)
        # - https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html
        kwargs['config'] = botocore.config.Config(
            retries={
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )
    return boto3.resource(service, **kwargs)

def boto_client(service, region=None):
    """the boto3 'service' client is a lower-level construct compared to the boto3 'resource' client.
    it excludes some convenient functionality, like automatic pagination."""
    exceptions = ['route53', 's3']
    if service not in exceptions:
        ensure(region, "'region' is a required parameter for all services except: %s" % (', '.join(exceptions),))
    return boto3.client(service, region_name=region)

def boto_conn(pname_or_stackname, service, client=False):
    "convenience. returns a boto Resource or client for the given project or stack name, using the region found in the project config."
    fn = project_data_for_stackname if '--' in pname_or_stackname else project.project_data
    pdata = fn(pname_or_stackname)
    # prefer resource if possible
    fn = boto_client if client else boto_resource
    return fn(service, pdata['aws']['region'])

#
#
#

# Silviot, https://github.com/boto/boto3/issues/264
# not a bugfix, just a convenience wrapper
def tags2dict(tags):
    """Convert a tag list to a dictionary.

    Example:
        >>> t2d([{'Key': 'Name', 'Value': 'foobar'}])
        {'Name': 'foobar'}
    """
    if tags is None:
        return {}
    return {el['Key']: el['Value'] for el in tags}

def ec2_instance_list(state='running'):
    """returns a list of all ec2 instances in given `state`.
    default state is `running`. `None` is considered 'any state'."""
    known_states_str = ", ".join(ALL_EC2_STATES)
    err_msg = "unknown ec2 state %r; known states: %s and None (all states)" % (state, known_states_str)
    ensure(state is None or state in ALL_EC2_STATES, err_msg)

    conn = boto_resource('ec2', find_region())

    filters = []
    if state:
        filters = [
            {'Name': 'instance-state-name', 'Values': [state]}
        ]
    # probably not paginated, but we can specify 1000 results at once:
    # - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.ServiceResource.instances
    qs = conn.instances.filter(Filters=filters, MaxResults=1000)
    result = [ec2.meta.data for ec2 in qs]
    for ec2 in result:
        ec2['TagsDict'] = tags2dict(ec2['Tags'])
    return result

def find_ec2_instances(stackname, state='running', node_ids=None, allow_empty=False):
    "returns list of ec2 instances data for a *specific* stackname. Ordered by node index (1 to N)"
    # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
    conn = boto_conn(stackname, 'ec2')
    filters = [
        {'Name': 'tag:aws:cloudformation:stack-name', 'Values': [stackname]}
    ]
    # hypothesis is that this is causing filters to skip running instances, non-deterministically.
    # We'll try to filter the list in-memory instead (below)
    # if state:
    #    filters.append({'Name': 'instance-state-name', 'Values': [state]})

    # an instance-id looks like: i-011d46bf3978e5618
    # NOTE: only lifecycle._ec2_nodes_states uses `node_ids` and nothing is passing it node ids
    if node_ids:
        filters.append({'Name': 'instance-id', 'Values': node_ids})

    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.ServiceResource.instances
    ec2_instances = list(conn.instances.filter(Filters=filters))

    # hack, see problems with query above. this problem hasn't been replicated (yet) on boto3
    if state:
        state = [state] if '|' not in state else state.split('|')
        ec2_instances = [i for i in ec2_instances if i.state['Name'] in state]

    LOG.debug("find_ec2_instances returned: %s", [(e.id, e.state) for e in ec2_instances])

    # multiple instances are sorted by node asc
    ec2_instances = sorted(ec2_instances, key=lambda ec2inst: tags2dict(ec2inst.tags).get('Node', 0))

    LOG.debug("find_ec2_instances with filters %s returned: %s", filters, [e.id for e in ec2_instances])
    if not allow_empty and not ec2_instances:
        raise NoRunningInstancesError("found no running ec2 instances for %r. The stack nodes may have been stopped, but here we were requiring them to be running" % stackname)
    return ec2_instances

# NOTE: preserved for the commentary, but this is for boto2
def _all_nodes_filter(stackname, node_ids):
    query = {
        # tag-key+tag-value is misleading here:
        # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
        #     tag-key - The key of a tag assigned to the resource. This filter is independent of the tag-value filter. For example, if you use both the filter "tag-key=Purpose" and the filter "tag-value=X", you get any resources assigned both the tag key Purpose (regardless of what the tag's value is), and the tag value X (regardless of what the tag's key is). If you want to list only resources where Purpose is X, see the tag:key=value filter.
        # 'tag-key': ['Cluster', 'Name'],
        # we cannot use 'tag-Cluster' and 'tag-name', because:
        # http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_Filtering.html
        #     In many cases, you can granulate the results by using complementary search terms on different key fields, where the AND rule is automatically applied instead. If you search for tag: Name:=All values and tag:Instance State=running, you get search results that contain both those criteria.
        # and that means we would be too selective, requiring *both* tags to be present when we wanted to select "at least one out of two"
        # Therefore, we check for this documented tag automatically created by
        # Cloudformation
        'tag:aws:cloudformation:stack-name': [stackname],
    }
    # hypothesis is that this is causing filters to skip running instances, non-deterministically. We'll try to filter the list in-memory instead
    # if state:
    #    query['instance-state-name'] = [state]
    if node_ids:
        query['instance-id'] = node_ids
    return query

#
#
#

def rds_iid(stackname, replacement_number=None):
    """generates a suitable RDS instance ID for the given `stackname`.
    the RDS instance ID needs to be deterministic or we need to find an attached RDS db without knowing it's name.
    - https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html#options"""
    ensure(stackname and isinstance(stackname, str), "given stackname must be a non-empty string.")
    max_rds_iid = 63
    slug = slugify(stackname) # "lax--prod" => "lax-prod"
    ensure(slug, "given stackname cannot slugify to an empty string.")
    if replacement_number and replacement_number > 0:
        slug = "%s-%s" % (slug, replacement_number) # "lax-prod" => "lax-prod-1"
    ensure(len(slug) <= max_rds_iid,
           "a database instance identifier must be less than 64 characters. %r is %s characters long." % (slug, len(slug)))
    return slug

def find_rds_instances(stackname):
    """returns a list of RDS instances attached to the given `stackname`.
    it is possible for multiple RDS instances to be returned if the stack is replacing an RDS instance and is mid-transition."""
    try:
        conn = boto_conn(stackname, 'rds', client=True) # RDS has no 'resource'

        # lsh@2022-05-20: rds instance id can no longer be generated from the `stackname` alone.
        # rds instances can now be replaced and the replacement number is incorporated into the rds instance id.
        context = context_handler.load_context(stackname)
        rid = rds_iid(stackname, lookup(context, 'rds.num-replacements', None))

        # lsh@2022-05-24: `rds_iid` will either return an ID or raise an AssertionError.
        # if rid:
        #    return conn.describe_db_instances(DBInstanceIdentifier=rid)['DBInstances']

        return conn.describe_db_instances(DBInstanceIdentifier=rid)['DBInstances']
    except AssertionError:
        # invalid dbid. RDS doesn't exist because stack couldn't have been created with this ID
        return []

    except botocore.exceptions.ClientError as err:
        LOG.info(err.response)
        invalid_dbid = "Invalid database identifier"
        if err.response['Error']['Message'].startswith(invalid_dbid):
            # what we asked for isn't a valid db id, we probably made a mistake.
            # we definitely couldn't have created a db with that id.
            return []

        if err.response['Error']['Code'] == 'DBInstanceNotFound':
            return []

        raise

def find_all_rds_instances():
    "returns a list of DBInstance dicts, straight from boto."
    # warning: not paginated, ~18 results at time of writing.
    conn = boto3.client('rds', region_name=find_region())
    results = conn.describe_db_instances(MaxRecords=100)['DBInstances']
    for i, row in enumerate(results):
        results[i]['TagsDict'] = tags2dict(row['TagList'])
    return results

#
#
#

def stack_pem(stackname, die_if_exists=False, die_if_doesnt_exist=False):
    """returns the path to the private key on the local filesystem.
    helpfully dies in different ways if you ask it to"""
    expected_key = join(config.KEYPAIR_PATH, stackname + ".pem")
    # for when we really need it to exist
    if die_if_doesnt_exist and not os.path.exists(expected_key):
        raise OSError("keypair %r not found at %r" % (stackname, expected_key))
    if die_if_exists and os.path.exists(expected_key):
        raise OSError("keypair %r found at %r, not overwriting." % (stackname, expected_key))
    return expected_key

def _ec2_connection_params(stackname, username, **kwargs):
    "returns a dictionary of settings to be used with `command.settings` context manager"
    params = {'user': username}
    pem = stack_pem(stackname)
    # handles cases where we want to establish a connection to run a task
    # when machine has failed to provision correctly.
    if username == config.BOOTSTRAP_USER:
        if os.path.exists(pem):
            params['key_filename'] = pem
        else:
            msg = "Attempting to connect to %s as the BOOTSTRAP_USER (%s) but the private key is missing (%s). Remote operations may fail if the public key for this user (%s) is not in the remote user's '/home/%s/.ssh/authorized_keys' file." % (
                stackname, config.BOOTSTRAP_USER, pem, config.WHOAMI, config.BOOTSTRAP_USER)
            LOG.warning(msg)
    params.update(kwargs)
    return params

@contextmanager
def stack_conn(stackname, username=config.DEPLOY_USER, node=None, **kwargs):
    ensure('user' not in kwargs, "found key 'user' in given kwargs - did you mean 'username'?")
    data = ec2_data(stackname, state='running')
    ensure(len(data) == 1 or node, "stack is clustered with %s nodes and no specific node provided" % len(data))
    node and ensure(utils.isint(node) and int(node) > 0, "given node must be an integer and greater than zero")
    didx = int(node) - 1 if node else 0 # decrement to a zero-based value
    data = data[didx] # data is ordered by node
    public_ip = data['PublicIpAddress']
    params = _ec2_connection_params(stackname, username, host_string=public_ip)

    with settings(**params):
        yield

class NoPublicIpsError(Exception):
    pass

def all_node_params(stackname):
    "returns a map of node data"
    data = ec2_data(stackname, state='running')
    public_ips = {ec2['InstanceId']: ec2.get('PublicIpAddress') for ec2 in data}
    nodes = {
        ec2['InstanceId']: int(tags2dict(ec2['Tags'])['Node'])
        if 'Node' in tags2dict(ec2['Tags'])
        else 1
        for ec2 in data
    }

    # copied from stack_all_ec2_nodes. probably not the most robust.
    params = _ec2_connection_params(stackname, config.DEPLOY_USER)

    # custom for builder, these are available inside workfn as `command.env('public_ips')`
    params.update({
        'stackname': stackname,
        'public_ips': public_ips,
        'nodes': nodes
    })

    return params

def stack_all_ec2_nodes(stackname, workfn, username=config.DEPLOY_USER, concurrency=None, node=None, instance_ids=None, num_attempts=6, **kwargs):
    """Executes `workfn` on all EC2 nodes of `stackname`.
    Optionally connects with the specified `username`."""
    work_kwargs = {}
    if isinstance(workfn, tuple):
        workfn, work_kwargs = workfn

    data = ec2_data(stackname, state='running')
    # TODO: reuse all_node_params?
    public_ips = {ec2['InstanceId']: ec2.get('PublicIpAddress') for ec2 in data}
    nodes = {ec2['InstanceId']: int(tags2dict(ec2['Tags'])['Node']) if 'Node' in tags2dict(ec2['Tags']) else 1 for ec2 in data}
    if node:
        nodes = {k: v for k, v in nodes.items() if v == int(node)}
        public_ips = {k: v for k, v in public_ips.items() if k in nodes}
    elif instance_ids:
        nodes = {k: v for k, v in nodes.items() if k in instance_ids}
        public_ips = {k: v for k, v in public_ips.items() if k in nodes}

    if not public_ips:
        LOG.info("No EC2 nodes to execute on")
        # should be a dictionary mapping ip address to result
        return {}

    params = _ec2_connection_params(stackname, username)
    params.update(kwargs)

    # custom for builder, these are available inside workfn as `command.env('public_ips')`
    params.update({
        'stackname': stackname,
        'public_ips': public_ips,
        'nodes': nodes
    })

    LOG.info("Executing on ec2 nodes (%s), concurrency %s", public_ips, concurrency)

    ensure(all(public_ips.values()), "Public ips are not valid: %s" % public_ips, NoPublicIpsError)

    def single_node_work_fn():
        last_exc = None
        for attempt in range(num_attempts):
            if attempt != 0:
                # attempt 0 is skipped, attempt 1 is 4sec, attempt 2 is 6sec, then 8sec, then 10sec, ...
                sleep_amt = 2 * (attempt + 1)
                # "attempt 2 of 6, pausing for 4secs ..."
                LOG.info("attempt %s of %s, pausing for %ssecs ...", attempt + 1, num_attempts, sleep_amt)
                time.sleep(sleep_amt)
            try:
                return workfn(**work_kwargs)
            except NetworkError as err:
                # "NetworkError executing task on foo--bar--1 during attempt 2: rsync returned error 30: Timeout in data send/receive."
                instance_id = "%s--%s" % (stackname, current_node_id())
                LOG.exception("NetworkError executing task on %s during attempt %s", instance_id, attempt + 1)
                last_exc = err
                continue

            except (ConnectionError, ConnectionRefusedError, NetworkTimeoutError, NetworkUnknownHostError, NetworkAuthenticationError) as err:
                # "low level network error executing task on foo--bar--1 during attempt 2: connection refused"
                instance_id = "%s--%s" % (stackname, current_node_id())
                LOG.exception("low level network error executing task on %s during attempt %s", stackname, attempt + 1)
                last_exc = err
                continue

            except CommandError:
                # "command aborted while executing on foo--bar--1 during attempt 2."
                instance_id = "%s--%s" % (stackname, current_node_id())
                LOG.exception("command aborted while executing on %s during attempt %s", instance_id, attempt + 1)
                raise

        if last_exc:
            raise last_exc
        return None

    params.update({
        'display_aborts': False
    })

    if not concurrency:
        concurrency = 'parallel'

    if concurrency == 'serial':
        return serial_work(single_node_work_fn, params)

    if concurrency == 'parallel':
        return parallel_work(single_node_work_fn, params)

    if callable(concurrency):
        return concurrency(single_node_work_fn, params)

    raise RuntimeError("Concurrency mode not supported: %s" % concurrency)

def serial_work(single_node_work, params):
    with settings(**params):
        return command.execute(command.serial(single_node_work), hosts=list(params['public_ips'].values()))

def parallel_work(single_node_work, params):
    with settings(**params):
        return command.execute(command.parallel(single_node_work), hosts=list(params['public_ips'].values()))

def current_ec2_node_id():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Sticking to the 'node' terminology because 'instance' is too overloaded.

    Sample value: 'i-0553487b4b6916bc9'"""

    ensure('host_string' in env() and env('host_string') is not None, "This is supposed to be called with settings for connecting to an EC2 instance")
    current_public_ip = env('host_string')

    ensure('public_ips' in env(), "This is supposed to be called by stack_all_ec2_nodes, which provides the correct configuration")
    matching_instance_ids = [instance_id for (instance_id, public_ip) in env('public_ips').items() if current_public_ip == public_ip]

    ensure(len(matching_instance_ids) == 1, "Too many instance ids (%s) pointing to this ip (%s)" % (matching_instance_ids, current_public_ip))
    return matching_instance_ids[0]

def current_node_id():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns a number from 1 to N (usually a small number, like 2) indicating how the current node has been numbered on creation to distinguish it from the others"""
    ec2_id = current_ec2_node_id()
    ensure(ec2_id in env('nodes'), "Can't find %s in %s node map" % (ec2_id, env('nodes')))
    return env('nodes')[ec2_id]

def current_ip():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns the ip address used to access the current host, e.g. '54.243.19.153'"""
    return env('host_string')

def current_stackname():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns the name of the stack the task is working on, e.g. 'journal--end2end'"""
    return env('stackname')

#
# stackname wrangling
#

def mk_stackname(project_name, instance_id):
    return "%s--%s" % (project_name, instance_id)

def parse_stackname(stackname, all_bits=False, idx=False):
    "returns a pair of (project, instance-id) by default, optionally returns the cluster (node) id if all_bits=True"
    if not stackname or not isstr(stackname):
        raise ValueError("stackname must look like <pname>--<instance-id>[--<cluster-id>], got: %r" % stackname)
    # https://docs.python.org/2/library/stdtypes.html#str.split
    bits = stackname.split('--', -1 if all_bits else 1)
    ensure(len(bits) > 1, "could not parse given stackname %r" % stackname, ValueError)
    if idx:
        bit_keys = ['project_name', 'instance_id', 'cluster_id'][:len(bits)]
        bits = dict(zip(bit_keys, bits))
    return bits

def prune_stackname(stackname):
    """converts a 'pname--iid' or 'pname--iid--nid' style stackname to just 'pname--iid'.
    invalid stacknames return None."""
    try:
        bits = parse_stackname(stackname, all_bits=True)
        return "--".join(bits[:2])
    except ValueError:
        return None

def stackname_parseable(stackname):
    "returns true if the given stackname can be parsed"
    try:
        parse_stackname(stackname)
        return True
    except ValueError:
        return False

def project_name_from_stackname(stackname):
    "returns just the project name from the given stackname"
    return first(parse_stackname(stackname))

def is_master_server_stack(stackname):
    return 'master-server--' in str(stackname)

#
# stack file wrangling
# stack 'files' are the things on the file system in the `.cfn/stacks/` dir.
#

def stack_path(stackname):
    "returns the expected path to a stack JSON file given a `stackname`."
    return join(config.STACK_PATH, stackname) + ".json"

#
# aws stack wrangling
# 'aws stacks' are stack files that have been given to AWS and provisioned.
#

# DO NOT CACHE.
# this function is polled to get the state of the stack when creating/updating/deleting.
def describe_stack(stackname, allow_missing=False):
    "returns the full details of a stack given it's name or ID"
    cfn = boto_conn(stackname, 'cloudformation')
    try:
        return first(list(cfn.stacks.filter(StackName=stackname)))
    except botocore.exceptions.ClientError as ex:
        if allow_missing and ex.response['Error']['Message'].endswith('does not exist'):
            return None
        raise

class NoRunningInstancesError(Exception):
    pass

def ec2_data(stackname, state=None):
    """returns a list of raw boto3 EC2.Instance data for ec2 instances attached to given `stackname`.
    does not filter by state by default.
    does not enforce single instance checking."""
    try:
        ec2_instances = find_ec2_instances(stackname, state=state, allow_empty=True)
        return [ec2.meta.data for ec2 in ec2_instances]
    except Exception:
        LOG.exception('unhandled exception attempting to discover more information about this instance. Instance may not exist yet.')
        raise


# DO NOT CACHE: function is used in polling
def stack_is(stackname, acceptable_states, terminal_states=None):
    "returns True if the given stack is in one of acceptable_states"
    terminal_states = terminal_states or []
    try:
        description = describe_stack(stackname)
        if description.stack_status in terminal_states:
            LOG.error("stack_status is '%s', cannot move from that\nDescription: %s", description.stack_status, description.meta.data)
            raise RuntimeError("stack status is '%s'" % description.stack_status)
        result = description.stack_status in acceptable_states
        if not result:
            LOG.info("stack_status is '%s'\nDescription: %s", description.stack_status, description.meta.data)
        return result
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Message'].endswith('does not exist'):
            LOG.info("stack %r does not exist", stackname)
            return False
        LOG.warning("unhandled exception testing state of stack %r", stackname)
        raise

# DO NOT CACHE: function is used in polling
def stack_is_active(stackname):
    "returns `True` if `stackname` is in a completed state"
    return stack_is(stackname, ACTIVE_CFN_STATUS)

def stack_exists(stackname, state=None):
    """convenience wrapper around `stack_is`. returns `True` if the stack exists else `False`.
    if `state` is 'steady', stack must also be in a non-transitioning 'steady' state.
    if `state` is 'active', stack must also be in a healthy 'active' state (no failed updates, etc).

    lsh@2021-11: added so CI can differentiate between existence/steadiness/healthiness of stack."""
    allowed_states = {
        None: ALL_CFN_STATUS,
        'steady': STEADY_CFN_STATUS,
        'active': ACTIVE_CFN_STATUS,
        # 'unsteady': UNSTEADY_CFN_STATUS,
    }
    msg = ', '.join(sorted(map(str, allowed_states.keys())))
    ensure(state in allowed_states, "unsupported state label %r. supported states: %s" % (state, msg))
    return stack_is(stackname, allowed_states[state])

def stack_triple(aws_stack):
    "returns a triple of (name, status, data) of stacks."
    return (aws_stack['StackName'], aws_stack['StackStatus'], aws_stack)

#
# lists of aws stacks
#

@cached
def _aws_stacks(region, status=None, formatter=stack_triple):
    "returns all stacks, even stacks deleted in the last 90 days, optionally filtered by status"
    # NOTE: uses boto3 client interface rather than resource interface
    # resource interface cannot filter by stack status
    paginator = boto_client('cloudformation', region).get_paginator('list_stacks')
    paginator = paginator.paginate(StackStatusFilter=status or [])
    results = utils.shallow_flatten([row['StackSummaries'] for row in paginator])
    if formatter:
        return lmap(formatter, results)
    return results

def active_aws_stacks(region, *args, **kwargs):
    "returns all stacks that are healthy"
    return _aws_stacks(region, ACTIVE_CFN_STATUS, *args, **kwargs)

def steady_aws_stacks(region, *args, **kwargs):
    "returns all stacks that are not in a transitionary state"
    return _aws_stacks(region, STEADY_CFN_STATUS, *args, **kwargs)

def active_aws_project_stacks(pname):
    "returns all active stacks for a given project name"
    pdata = project.project_data(pname)
    region = pdata['aws']['region']

    def fn(triple):
        stackname = first(triple)
        if stackname_parseable(stackname):
            return project_name_from_stackname(stackname) == pname
        return None
    return lfilter(fn, active_aws_stacks(region))

def stack_names(stack_list, only_parseable=True):
    """returns the names of all CloudFormation stacks.
    set `only_parseable` to `False` to include stacks not managed by builder."""
    results = sorted(map(first, stack_list))
    if only_parseable:
        return lfilter(stackname_parseable, results)
    return results

def active_stack_names(region):
    "convenience. returns names of all active stacks"
    return stack_names(active_aws_stacks(region))

def steady_stack_names(region):
    "convenience. returns names of all stacks in a non-transitory state"
    return stack_names(steady_aws_stacks(region))

class MultipleRegionsError(EnvironmentError):
    def __init__(self, regions):
        super().__init__()
        self._regions = regions

    def regions(self):
        return self._regions

def find_region(stackname=None):
    """used when we haven't got a stack and need to know about stacks in a particular region.
    if a stack is provided, it uses the one provided in it's configuration.
    otherwise, generates a list of used regions from project data

    if more than one region available, it will raise an MultipleRegionsError.
    until we have some means of supporting multiple regions, this is the best solution"""
    if stackname:
        # TODO: should use context, not project data
        # as updates in project data do not immediately affect existing stacks
        # which reside in a region
        pdata = project_data_for_stackname(stackname)
        return pdata['aws']['region']

    all_projects = project.project_map()
    all_regions = [lookup(p, 'aws.region', None) for p in all_projects.values()]
    region_list = unique(filter(None, all_regions)) # remove any Nones, make unique, make a list
    if not region_list:
        msg = "no regions available at all!"
        raise OSError(msg)
    if len(region_list) > 1:
        raise MultipleRegionsError(region_list)
    return region_list[0]

def find_master(region):
    """returns the name of the master-server for the given `region`, which should be the same for all regions.
    master-server instances used to be datestamped so that one could be brought up while the other would
    continue to serve the minions and the right master-server (the oldest one) would need to be returned."""
    return config.MASTER_SERVER_IID

def find_master_for_stack(stackname):
    "convenience. finds the master server for the same region as given stack"
    pdata = project_data_for_stackname(stackname)
    return find_master(pdata['aws']['region'])

#
# decorators
#

def requires_active_stack(func):
    "requires a stack instance to exist in a successfully created/updated state"
    return decorators._requires_fn_stack(func, stack_is_active)

def requires_stack_file(func):
    """requires a stack template to exist on disk.
    see `src.decorators.requires_aws_stack_template` for a task decorator that downloads
    template and writes it to disk if it doesn't exist."""
    msg = "failed to find cloudformation stack template for %(stackname)r in: " + config.STACK_PATH
    return decorators._requires_fn_stack(func, lambda stackname: os.path.exists(stack_path(stackname)), msg)

#
#
#

def project_data_for_stackname(stackname):
    """like `project.project_data` but modifies the project data if the instance-id
    extracted from the given `stackname` matches a project alt-config.
    does nothing for ad-hoc instance using an alt-config."""
    (pname, instance_id) = parse_stackname(stackname)
    project_data = project.project_data(pname)
    if 'aws-alt' in project_data and instance_id in project_data['aws-alt']:
        project_data = project.set_project_alt(project_data, 'aws', instance_id)
    if 'gcp-alt' in project_data and instance_id in project_data['gcp-alt']:
        project_data = project.set_project_alt(project_data, 'gcp', instance_id)
    return project_data


#
# AWS configuration drift
#

def drift_check(stackname):
    "returns a list of resources that have drifted for the given `stackname`"
    conn = boto_conn(stackname, 'cloudformation', client=True)

    handle = conn.detect_stack_drift(StackName=stackname)
    handle = handle['StackDriftDetectionId']

    def is_detecting_drift():
        job = conn.describe_stack_drift_detection_status(StackDriftDetectionId=handle)
        return job.get('DetectionStatus') == 'DETECTION_IN_PROGRESS'
    utils.call_while(is_detecting_drift, interval=config.AWS_POLLING_INTERVAL, update_msg='Waiting for drift results ...')

    result = conn.describe_stack_resource_drifts(StackName=stackname)
    drifted = [resource for resource in result["StackResourceDrifts"] if resource["StackResourceDriftStatus"] != "IN_SYNC"]
    return drifted or None


# migrated from bootstrap.py
# might need a better home


# TODO: move to buildercore.cloudformation?
@requires_active_stack
def template_info(stackname):
    "returns some useful information about the given stackname as a map"
    data = describe_stack(stackname).meta.data

    # limit what this function returns in the interests of being explicit on what is supported.
    keepers = OrderedDict([
        ('StackName', 'stack_name'),
        ('StackId', 'stack_id'),
        ('Outputs', 'outputs')
    ])

    # preserve the lowercase+underscore formatting of original boto2 struct now that we're using boto3
    utils.renkeys(data, keepers.items())

    # replaces the standand 'list-of-dicts' outputs with a simpler dict
    data['outputs'] = {o['OutputKey']: o['OutputValue'] for o in data.get('outputs', [])}

    return subdict(data, keepers.values())

def remove_minion_key(stackname):
    "removes all keys for all nodes of the given stackname from the master server"
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    master_stack = find_master(region)
    with stack_conn(master_stack):
        command.remote_sudo("rm -f /etc/salt/pki/master/minions/%s--*" % stackname)

def write_environment_info(stackname, overwrite=False):
    """Looks for /etc/cfn-info.json and writes one if not found.
    Must be called with an active stack connection.

    This gives Salt the outputs available at stack creation, but that were not
    available at template compilation time.
    """
    if not command.remote_file_exists("/etc/cfn-info.json") or overwrite:
        LOG.info('no cfn outputs found or overwrite=True, writing /etc/cfn-info.json ...')
        infr_config = utils.json_dumps(template_info(stackname))
        return command.put_data(infr_config, "/etc/cfn-info.json", use_sudo=True)
    LOG.debug('cfn outputs found, skipping.')
    return []
