"""this module appears to be where I collect functionality
that is built upon by the more specialised parts of builder.

suggestions for a better name than 'core' welcome."""

import os, glob, json, re
from os.path import join
from . import utils, config, project, decorators # BE SUPER CAREFUL OF CIRCULAR DEPENDENCIES
from .decorators import testme
from .utils import ensure, first, lookup, lmap, lfilter, unique, isstr
import boto3
import botocore
from contextlib import contextmanager
from fabric.api import settings, execute, env, parallel, serial, hide, run, sudo
from fabric.exceptions import NetworkError
from fabric.state import output
from slugify import slugify
import logging
from kids.cache import cache as cached

LOG = logging.getLogger(__name__)
boto3.set_stream_logger(name='botocore', level=logging.INFO)

class DeprecationException(Exception):
    pass

class NoMasterException(Exception):
    pass


ALL_CFN_STATUS = [
    'CREATE_IN_PROGRESS',
    'CREATE_FAILED',
    'CREATE_COMPLETE',
    'ROLLBACK_IN_PROGRESS',
    'ROLLBACK_FAILED',
    'ROLLBACK_COMPLETE',
    'DELETE_IN_PROGRESS',
    'DELETE_FAILED',
    'UPDATE_IN_PROGRESS',
    'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_COMPLETE',
    'UPDATE_ROLLBACK_IN_PROGRESS',
    'UPDATE_ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_ROLLBACK_COMPLETE',
]

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
    #'DELETE_COMPLETE', # technically true, but we can't do anything with them
    'UPDATE_COMPLETE',
    'UPDATE_ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_COMPLETE',
]

#
# sns
#

def _all_sns_subscriptions(region):
    paginator = boto_client('sns', region).get_paginator('list_subscriptions')
    return utils.shallow_flatten([page['Subscriptions'] for page in paginator.paginate()])

def all_sns_subscriptions(region, stackname=None):
    """returns all subscriptions to all sns topics.
    optionally filtered by subscription endpoints matching given stack"""
    subs_list = _all_sns_subscriptions(region)
    if stackname:
        # a subscription looks like:
        # {u'Endpoint': u'arn:aws:sqs:us-east-1:512686554592:observer--substest1',
        #  u'Owner': u'512686554592',
        #  u'Protocol': u'sqs',
        #  u'SubscriptionArn': u'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1:f44c42db-81c0-4504-b3de-51b0fb1099ff',
        #  u'TopicArn': u'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1'}
        subs_list = lfilter(lambda row: row['Endpoint'].endswith(stackname), subs_list)

    # add a 'Topic' key for easier filtering downstream
    # 'arn:aws:sns:us-east-1:512686554592:bus-articles--substest1' => 'bus-articles--substest1'
    lmap(lambda row: row.update({'Topic': row['TopicArn'].split(':')[-1]}), subs_list)
    return subs_list

#
#
#

def boto_resource(service, region):
    return boto3.resource(service, region_name=region)

def boto_client(service, region=None):
    """the boto3 service client is a lower-level construct compared to the boto3 resource client.
    it excludes some convenient functionality, like automatic pagination.
    prefer the service resource over the client"""
    exceptions = ['route53']
    if service not in exceptions:
        ensure(region, "'region' is a required parameter for all services except: %s" % (', '.join(exceptions),))
    return boto3.client(service, region_name=region)

def boto_conn(pname_or_stackname, service, client=False):
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
    return dict((el['Key'], el['Value']) for el in tags)

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
        raise NoRunningInstances("found no running ec2 instances for %r. The stack nodes may have been stopped, but here we were requiring them to be running" % stackname)
    return ec2_instances

# NOTE: preserved for the commentary, but this is for boto2
def _all_nodes_filter(stackname, node_ids):
    query = {
        # tag-key+tag-value is misleading here:
        # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
        #     tag-key - The key of a tag assigned to the resource. This filter is independent of the tag-value filter. For example, if you use both the filter "tag-key=Purpose" and the filter "tag-value=X", you get any resources assigned both the tag key Purpose (regardless of what the tag's value is), and the tag value X (regardless of what the tag's key is). If you want to list only resources where Purpose is X, see the tag:key=value filter.
        #'tag-key': ['Cluster', 'Name'],
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

def rds_dbname(stackname, context=None):
    # TODO: investigate possibility of ambiguous RDS naming here
    context = context or {}
    return context.get('rds_dbname') or slugify(stackname, separator="") # *must* use 'or' here

def rds_iid(stackname):
    max_rds_iid = 63 # https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html#options
    # the rds iid needs to be deterministic, or, we need to find an attached rds db without knowing it's name
    slug = slugify(stackname)
    ensure(len(slug) <= max_rds_iid, "a database instance identifier must be less than 64 characters")
    return slug

def find_rds_instances(stackname, state='available'):
    "This uses boto3 because it allows to start/stop instances"
    try:
        conn = boto_conn(stackname, 'rds', client=True) # RDS has no 'resource'
        rid = rds_iid(stackname)
        if rid:
            # TODO: return the first (and only) result of DBInstances
            return conn.describe_db_instances(DBInstanceIdentifier=rid)['DBInstances']
    except AssertionError:
        # invalid dbid. RDS doesn't exist because stack couldn't have been created with this ID
        return []

    except botocore.exceptions.ClientError as err:
        LOG.info(err.response)
        invalid_dbid = "Invalid database identifier"
        if err.response['Error']['Message'].startswith(invalid_dbid):
            # what we asked for isn't a valid db id, we probably made a mistake
            # we definitely couldn't have created a db with that id
            return []

        if err.response['Error']['Code'] == 'DBInstanceNotFound':
            return []

        raise err

#
#
#

def stack_pem(stackname, die_if_exists=False, die_if_doesnt_exist=False):
    """returns the path to the private key on the local filesystem.
    helpfully dies in different ways if you ask it to"""
    expected_key = join(config.KEYPAIR_PATH, stackname + ".pem")
    # for when we really need it to exist
    if die_if_doesnt_exist and not os.path.exists(expected_key):
        raise EnvironmentError("keypair %r not found at %r" % (stackname, expected_key))
    if die_if_exists and os.path.exists(expected_key):
        raise EnvironmentError("keypair %r found at %r, not overwriting." % (stackname, expected_key))
    return expected_key

def _ec2_connection_params(stackname, username, **kwargs):
    "returns a dictionary of settings to be used with Fabric's api.settings context manager"
    # http://docs.fabfile.org/en/1.14/usage/env.html
    params = {'user': username}
    pem = stack_pem(stackname)
    # handles cases where we want to establish a connection to run a task
    # when machine has failed to provision correctly.
    if username == config.BOOTSTRAP_USER:
        if os.path.exists(pem):
            params['key_filename'] = pem
        else:
            LOG.error("private key for the bootstrap user for this host does not exist. I looked here: %s" % pem)
            #raise RuntimeError("private key for the bootstrap user for this host does not exist. I looked here: %s" % pem)
    params.update(kwargs)
    return params

@contextmanager
def stack_conn(stackname, username=config.DEPLOY_USER, node=None, **kwargs):
    if 'user' in kwargs:
        LOG.warn("found key 'user' in given kwargs - did you mean 'username' ??")

    data = stack_data(stackname, ensure_single_instance=False)
    ensure(len(data) == 1 or node, "stack is clustered with %s nodes and no specific node provided" % len(data))
    node and ensure(utils.isint(node) and int(node) > 0, "given node must be an integer and greater than zero")
    didx = int(node) - 1 if node else 0 # decrement to a zero-based value
    data = data[didx] # data is ordered by node
    public_ip = data['PublicIpAddress']
    params = _ec2_connection_params(stackname, username, host_string=public_ip)

    with settings(**params):
        yield

class NoPublicIps(Exception):
    pass

def all_node_params(stackname):
    data = stack_data(stackname)
    public_ips = {ec2['InstanceId']: ec2.get('PublicIpAddress') for ec2 in data}
    nodes = {ec2['InstanceId']: int(tags2dict(ec2['Tags'])['Node']) if 'Node' in tags2dict(ec2['Tags']) else 1 for ec2 in data}

    # TODO: default copied from stack_all_ec2_nodes, but not the most robust probably
    params = _ec2_connection_params(stackname, config.DEPLOY_USER)

    # custom for builder, these are available as fabric.api.env.public_ips inside workfn
    params.update({
        'stackname': stackname,
        'public_ips': public_ips,
        'nodes': nodes
    })

    return params

def stack_all_ec2_nodes(stackname, workfn, username=config.DEPLOY_USER, concurrency=None, node=None, instance_ids=None, **kwargs):
    """Executes work on all the EC2 nodes of stackname.
    Optionally connects with the specified username"""
    work_kwargs = {}
    if isinstance(workfn, tuple):
        workfn, work_kwargs = workfn

    data = stack_data(stackname)
    # TODO: reuse all_node_params?
    public_ips = {ec2['InstanceId']: ec2.get('PublicIpAddress') for ec2 in data}
    nodes = {ec2['InstanceId']: int(tags2dict(ec2['Tags'])['Node']) if 'Node' in tags2dict(ec2['Tags']) else 1 for ec2 in data}
    if node:
        nodes = {k: v for k, v in nodes.items() if v == int(node)}
        public_ips = {k: v for k, v in public_ips.items() if k in nodes.keys()}
    elif instance_ids:
        nodes = {k: v for k, v in nodes.items() if k in instance_ids}
        public_ips = {k: v for k, v in public_ips.items() if k in nodes.keys()}

    params = _ec2_connection_params(stackname, username)
    params.update(kwargs)

    # custom for builder, these are available as fabric.api.env.public_ips inside workfn
    params.update({
        'stackname': stackname,
        'public_ips': public_ips,
        'nodes': nodes
    })

    if not public_ips:
        LOG.info("No EC2 nodes to execute on")
        # should be a dictionary mapping ip address to result
        return {}

    LOG.info("Executing on ec2 nodes (%s), concurrency %s", public_ips, concurrency)

    ensure(all(public_ips.values()), "Public ips are not valid: %s" % public_ips, NoPublicIps)

    # TODO: candidate for a @backoff decorator
    def single_node_work():
        for attempt in range(0, 6):
            try:
                return workfn(**work_kwargs)
            except NetworkError as err:
                if str(err).startswith('Timed out trying to connect'):
                    LOG.info("Timeout while executing task on a %s node (%s) during attempt %s, retrying on this node", stackname, err, attempt)
                    continue
                if str(err).startswith('Low level socket error connecting to host'):
                    LOG.info("Cannot connect to a %s node (%s) during attempt %s, retrying on this node", stackname, err, attempt)
                    continue
                else:
                    raise err
            except config.FabricException as err:
                LOG.error(str(err).replace("\n", "    "))
                # available as 'results' to fabric.tasks.error
                raise err

    # something less stateful like a context manager?
    output['aborts'] = False

    # TODO: extract in buildercore.concurrency
    if not concurrency:
        concurrency = 'parallel'

    if concurrency == 'serial':
        return serial_work(single_node_work, params)

    elif concurrency == 'parallel':
        return parallel_work(single_node_work, params)

    elif callable(concurrency):
        return concurrency(single_node_work, params)

    raise RuntimeError("Concurrency mode not supported: %s" % concurrency)

def serial_work(single_node_work, params):
    with settings(**params):
        return execute(serial(single_node_work), hosts=list(params['public_ips'].values()))

def parallel_work(single_node_work, params):
    with settings(**params):
        return execute(parallel(single_node_work), hosts=list(params['public_ips'].values()))

def current_ec2_node_id():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Sticking to the 'node' terminology because 'instance' is too overloaded.

    Sample value: 'i-0553487b4b6916bc9'"""

    ensure(env.host is not None, "This is supposed to be called with settings for connecting to an EC2 instance")
    current_public_ip = env.host

    ensure('public_ips' in env, "This is supposed to be called by stack_all_ec2_nodes, which provides the correct configuration")
    matching_instance_ids = [instance_id for (instance_id, public_ip) in env.public_ips.items() if current_public_ip == public_ip]

    ensure(len(matching_instance_ids) == 1, "Too many instance ids (%s) pointing to this ip (%s)" % (matching_instance_ids, current_public_ip))
    return matching_instance_ids[0]

def current_node_id():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns a number from 1 to N (usually a small number, like 2) indicating how the current node has been numbered on creation to distinguish it from the others"""
    ec2_id = current_ec2_node_id()
    ensure(ec2_id in env.nodes, "Can't find %s in %s node map" % (ec2_id, env.nodes))
    return env.nodes[ec2_id]

def current_ip():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns the ip address used to access the current host, e.g. '54.243.19.153'"""
    return env.host

def current_stackname():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Returns the name of the stack the task is working on, e.g. 'journal--end2end'"""
    return env.stackname

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
# TODO: consider shifting .cfn/stacks/ to /temp/stacks.
# rendered files simply accumulate, are never consulted and JSON can be captured from AWS if needs be
#

def parse_stack_file_name(stack_filename):
    "returns just the stackname sans leading dirs and trailing extensions given a path to a stack"
    stack = os.path.basename(stack_filename) # just the file
    return os.path.splitext(stack)[0] # just the filename

def stack_files():
    "returns a list of manually created cloudformation stacknames"
    stacks = glob.glob("%s/*.json" % config.STACK_PATH)
    return lmap(parse_stack_file_name, stacks)

def stack_path(stackname, relative=False):
    "returns the full path to a stack JSON file given a stackname"
    if stackname in stack_files():
        path = config.STACK_DIR if relative else config.STACK_PATH
        return join(path, stackname) + ".json"
    raise ValueError("could not find stack %r in %r" % (stackname, config.STACK_PATH))

# def stack_body(stackname):
#    stack = boto_conn(stackname, 'cloudformation', client=True)
#    return stack.get_template()['TemplateBody']

def stack_json(stackname, parse=False):
    "returns the json of the given stack as a STRING, not the parsed json unless `parse = True`."
    fp = open(stack_path(stackname), 'r')
    if parse:
        return json.load(fp)
    return fp.read()

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

class NoRunningInstances(Exception):
    pass

# TODO: misleading name, this returns a list of raw boto3 EC2.Instance data
def stack_data(stackname, ensure_single_instance=False):
    try:
        ec2_instances = find_ec2_instances(stackname, allow_empty=True)
        if len(ec2_instances) > 1 and ensure_single_instance:
            raise RuntimeError("talking to multiple EC2 instances is not supported for this task yet: %r" % stackname)
        return [ec2.meta.data for ec2 in ec2_instances]
    except Exception:
        LOG.exception('unhandled exception attempting to discover more information about this instance. Instance may not exist yet.')
        raise

# DO NOT CACHE
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
            return False
        LOG.warning("unhandled exception testing state of stack %r", stackname)
        raise

# DO NOT CACHE
def stack_is_active(stackname):
    "returns True if the given stack is in a completed state"
    return stack_is(stackname, ACTIVE_CFN_STATUS)

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
    return lfilter(fn, active_aws_stacks(region))

# TODO: consider removing `only_parseable` parameter.
def stack_names(stack_list, only_parseable=True):
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
        super(MultipleRegionsError, self).__init__()
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
        raise EnvironmentError("no regions available at all!")
    if len(region_list) > 1:
        raise MultipleRegionsError(region_list)
    return region_list[0]

@testme
def find_master_servers(stacks):
    "returns a list of master servers, oldest to newest"
    msl = lfilter(lambda triple: is_master_server_stack(first(triple)), stacks)
    msl = lmap(first, msl) # just stack names
    if len(msl) > 1:
        LOG.warn("more than one master server found: %s. this state should only ever be temporary.", msl)
    return sorted(msl, key=parse_stackname) # oldest to newest

def find_master(region):
    """returns the *oldest* aws master-server it can find.

    Since we are using the oldest, new master-server instances can be provisioned and debugged without being picked up until the older master-server is taken down"""
    stacks = active_aws_stacks(region)
    if not stacks:
        raise NoMasterException("no master servers found in region %r" % region)
    return first(find_master_servers(stacks))

def find_master_for_stack(stackname):
    "convenience. finds the master server for the same region as given stack"
    pdata = project_data_for_stackname(stackname)
    return find_master(pdata['aws']['region'])

#
# decorators
#

def requires_active_stack(func):
    "requires a stack to exist in a successfully created/updated state"
    return decorators._requires_fn_stack(func, stack_is_active)

def requires_stack_file(func):
    "requires a stack template to exist on disk"
    msg = "I couldn't find a cloudformation stack file for %(stackname)r!"
    return decorators._requires_fn_stack(func, lambda stackname: stackname in stack_files(), msg)

#
#
#

def hostname_struct(stackname):
    "returns a dictionary with convenient domain name information"
    # wrangle hostname data

    pname, instance_id = parse_stackname(stackname)
    pdata = project.project_data(pname)
    domain = pdata.get('domain')
    intdomain = pdata.get('intdomain')
    subdomain = pdata.get('subdomain')

    struct = {
        'domain': domain, # elifesciences.org
        'int_domain': intdomain, # elife.internal

        'subdomain': subdomain, # gateway

        'hostname': None, # temp.gateway

        'project_hostname': None, # gateway.elifesciences.org
        'int_project_hostname': None, # gateway.elife.internal

        'full_hostname': None, # gateway--temp.elifesciences.org
        'int_full_hostname': None, # gateway--temp.elife.internal
    }
    if not subdomain:
        # this project doesn't expect to be addressed
        # return immediately with what we do have
        return struct

    # removes any non-alphanumeric or hyphen characters
    instance_subdomain_fragment = re.sub(r'[^\w\-]', '', instance_id)
    hostname = instance_subdomain_fragment + "--" + subdomain

    updates = {
        'hostname': hostname,
    }

    if domain:
        updates['project_hostname'] = subdomain + "." + domain
        updates['full_hostname'] = hostname + "." + domain
        updates['ext_node_hostname'] = hostname + "--%s." + domain

    if intdomain:
        updates['int_project_hostname'] = subdomain + "." + intdomain
        updates['int_full_hostname'] = hostname + "." + intdomain
        updates['int_node_hostname'] = hostname + "--%s." + intdomain

    struct.update(updates)
    return struct

#
#
#

def project_data_for_stackname(stackname):
    (pname, instance_id) = parse_stackname(stackname)
    project_data = project.project_data(pname)
    if 'aws-alt' in project_data and instance_id in project_data['aws-alt']:
        project_data = project.set_project_alt(project_data, 'aws', instance_id)
    if 'gcp-alt' in project_data and instance_id in project_data['gcp-alt']:
        project_data = project.set_project_alt(project_data, 'gcp', instance_id)
    return project_data

def listfiles_remote(path=None, use_sudo=False):
    """returns a list of files in a directory at `path` as absolute paths"""
    ensure(path, "path to remote directory required")
    with hide('output'):
        runfn = sudo if use_sudo else run
        path = "%s/*" % path.rstrip("/")
        stdout = runfn("for i in %s; do echo $i; done" % path)
        if stdout == path: # some kind of bash artifact where it returns `/path/*` when no matches
            return []
        return stdout.splitlines()
