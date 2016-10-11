"""this module appears to be where I collect functionality
that is built upon by the more specialised parts of builder.

suggestions for a better name than 'core' welcome."""

import os, glob, json, re
from os.path import join
from . import utils, config, project, decorators # BE SUPER CAREFUL OF CIRCULAR DEPENDENCIES
from .decorators import testme
from .utils import first, lookup
from boto import sns
from boto.exception import BotoServerError
import boto3
from contextlib import contextmanager
from fabric.api import settings, execute, env
import importlib
import logging
from kids.cache import cache as cached
from slugify import slugify

LOG = logging.getLogger(__name__)
boto3.set_stream_logger(name='botocore')

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


def _set_raw_subscription_attribute(sns_connection, subscription_arn):
    """
    Works around boto's lack of a SetSubscriptionAttributes call.

    boto doesn't (yet) expose SetSubscriptionAttributes, so here's a
    monkeypatch specifically for turning on the RawMessageDelivery attribute.
    """
    params = {
        'AttributeName': 'RawMessageDelivery',
        'AttributeValue': 'true',
        'SubscriptionArn': subscription_arn
    }
    return sns_connection._make_request('SetSubscriptionAttributes', params)

sns.connection.SNSConnection.set_raw_subscription_attribute = _set_raw_subscription_attribute


#
#
#

def connect_aws(service, region):
    "connects to given service using the region in the "
    aliases = {
        'cfn': 'cloudformation'
    }
    service = service if service not in aliases else aliases[service]
    conn = importlib.import_module('boto.%s' % service)
    return conn.connect_to_region(region)

@cached
def boto_cfn_conn(region):
    return connect_aws('cloudformation', region)

@cached
def boto_ec2_conn(region):
    return connect_aws('ec2', region)

@cached
def boto_sns_conn(region):
    return connect_aws('sns', region)

@cached
def boto_sqs_conn(region):
    return connect_aws('sqs', region)

@cached
def boto_s3_conn(region):
    "This uses boto3 because it allows to set NotificationConfiguration for sending messages to SQS"
    return boto3.client('s3', region)

@cached
def connect_aws_with_pname(pname, service):
    "convenience"
    pdata = project.project_data(pname)
    region = pdata['aws']['region']
    print 'connecting to a', pname, 'instance in region', region
    return connect_aws(service, region)

def connect_aws_with_stack(stackname, service):
    "convenience"
    pname = project_name_from_stackname(stackname)
    return connect_aws_with_pname(pname, service)

def find_ec2_instances(stackname, state='running', node_ids=None):
    "returns list of ec2 instances data for a *specific* stackname"
    # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
    conn = connect_aws_with_stack(stackname, 'ec2')
    return conn.get_only_instances(filters=_all_nodes_filter(stackname, state=state, node_ids=node_ids))

def _all_nodes_filter(stackname, state, node_ids):
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
    if state:
        query['instance-state-name'] = [state]
    if node_ids:
        query['instance-id'] = node_ids
    return query

def find_ec2_volume(stackname):
    ec2_data = find_ec2_instances(stackname)[0]
    iid = ec2_data.id
    # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
    kwargs = {'filters': {'attachment.instance-id': iid}}
    return connect_aws_with_stack(stackname, 'ec2').get_all_volumes(**kwargs)

# should live in `keypair`, but I can't have `core` depend on `keypair` and viceversa
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
    params = {
        'user': username,
    }
    pem = stack_pem(stackname)
    # doesn't hurt, handles cases where we want to establish a connection to run a task
    # when machine has failed to provision correctly.
    if os.path.exists(pem) and username == config.BOOTSTRAP_USER:
        params.update({
            'key_filename': pem
        })
    params.update(kwargs)
    return params

@contextmanager
def stack_conn(stackname, username=config.DEPLOY_USER, **kwargs):
    if 'user' in kwargs:
        LOG.warn("found key 'user' in given kwargs - did you mean 'username' ??")

    data = stack_data(stackname, ensure_single_instance=True)[0]
    public_ip = data['ip_address']
    params = _ec2_connection_params(stackname, username, host_string=public_ip)

    with settings(**params):
        yield

def stack_all_ec2_nodes(stackname, workfn, username=config.DEPLOY_USER, **kwargs):
    """Executes work on all the EC2 nodes of stackname.
    Optionally connects with the specified username"""
    work_kwargs = {}
    if isinstance(workfn, tuple):
        workfn, work_kwargs = workfn

    public_ips = {ec2['id']: ec2['ip_address'] for ec2 in stack_data(stackname)}
    params = _ec2_connection_params(stackname, username)
    params.update(kwargs)
    # custom for builder, these are available as fabric.api.env.public_ips
    # inside workfn
    params.update({'public_ips': public_ips})
    LOG.info("Executing %s on all ec2 nodes (%s)", workfn, public_ips)

    with settings(**params):
        # TODO: decorate work to print what it is connecting only
        execute(workfn, hosts=public_ips.values(), **work_kwargs)

def current_ec2_node_id():
    """Assumes it is called inside the 'workfn' of a 'stack_all_ec2_nodes'.

    Sticking to the 'node' terminology because 'instance' is too overloaded."""

    assert env.host is not None, "This is supposed to be called with settings for connecting to an EC2 instance"
    current_public_ip = env.host

    assert 'public_ips' in env, "This is supposed to be called by stack_all_ec2_nodes, which provides the correct configuration"
    matching_instance_ids = [instance_id for (instance_id, public_ip) in env.public_ips.iteritems() if current_public_ip == public_ip]

    assert len(matching_instance_ids) == 1, ("Too many instance ids (%s) pointing to this ip (%s)" % (matching_instance_ids, current_public_ip))
    return matching_instance_ids[0]


#
# stackname wrangling
#

def mk_stackname(*bits):
    return "--".join(map(slugify, filter(None, bits)))

# TODO: test these functions
def parse_stackname(stackname, all_bits=False):
    "returns a pair of (project, instance-id) by default, optionally returns the cluster id if all_bits=True"
    if not stackname or not isinstance(stackname, basestring):
        raise ValueError("stackname must look like <pname>--<instance-id>[--<cluster-id>], got: %r" % str(stackname))
    # https://docs.python.org/2/library/stdtypes.html#str.split
    bits = stackname.split('--', -1 if all_bits else 1)
    if len(bits) == 1:
        raise ValueError("could not parse given stackname %r" % stackname)
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

def is_prod_stack(stackname):
    _, instance_id = parse_stackname(stackname)
    return instance_id in ['master', 'prod']


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
    return map(parse_stack_file_name, stacks)

def stack_path(stackname, relative=False):
    "returns the full path to a stack JSON file given a stackname"
    if stackname in stack_files():
        path = config.STACK_DIR if relative else config.STACK_PATH
        return join(path, stackname) + ".json"
    raise ValueError("could not find stack %r in %r" % (stackname, config.STACK_PATH))

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
def describe_stack(stackname):
    "returns the full details of a stack given it's name or ID"
    return first(connect_aws_with_stack(stackname, 'cfn').describe_stacks(stackname))

# TODO: rename or something
def stack_data(stackname, ensure_single_instance=False):
    """like `describe_stack`, but returns a list of dictionaries"""

    try:
        ec2_instances = find_ec2_instances(stackname)

        if len(ec2_instances) < 1:
            raise RuntimeError("found no running ec2 instances for %r. The stack nodes may have been stopped" % stackname)
        elif len(ec2_instances) > 1 and ensure_single_instance:
            raise RuntimeError("talking to multiple EC2 instances is not supported for this task yet: %r" % stackname)

        def ec2data(ec2):
            return ec2.__dict__
        return map(ec2data, ec2_instances)

    except Exception:
        LOG.exception('caught an exception attempting to discover more information about this instance. The instance may not exist yet ...')
        raise


# DO NOT CACHE
def stack_is_active(stackname):
    "returns True if the given stack is in a completed state"
    try:
        description = describe_stack(stackname)
        result = description.stack_status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
        if not result:
            LOG.info("stack_status is '%s'\nDescription: %s", description.stack_status, vars(description))
        return result
    except BotoServerError as err:
        if err.message.endswith('does not exist'):
            return False
        LOG.warning("unhandled exception testing active state of stack %r", stackname)
        raise

def stack_triple(aws_stack):
    "returns a triple of (name, status, data) of stacks."
    return (aws_stack.stack_name, aws_stack.stack_status, aws_stack)

#
# lists of aws stacks
#

@cached
def aws_stacks(region, status=None, formatter=stack_triple):
    "returns *all* stacks, even stacks deleted in the last 90 days"
    if not status:
        status = []
    # NOTE: avoid `.describe_stack` as the results are truncated beyond a certain amount
    # use `.describe_stack` on specific stacks only
    results = boto_cfn_conn(region).list_stacks(status)
    if formatter:
        return map(formatter, results)
    return results

def active_aws_stacks(region, *args, **kwargs):
    "returns all stacks that are healthy"
    return aws_stacks(region, ACTIVE_CFN_STATUS, *args, **kwargs)

def steady_aws_stacks(region):
    "returns all stacks that are not in a transitionary state"
    return aws_stacks(region, STEADY_CFN_STATUS)

def active_aws_project_stacks(pname):
    "returns all active stacks for a given project name"
    pdata = project.project_data(pname)
    region = pdata['aws']['region']
    fn = lambda t: project_name_from_stackname(first(t)) == pname
    return filter(fn, active_aws_stacks(region))

def stack_names(stack_list, only_parseable=True):
    results = sorted(map(first, stack_list))
    if only_parseable:
        return filter(stackname_parseable, results)
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
        pdata = project_data_for_stackname(stackname)
        return pdata['aws']['region']

    all_projects = project.project_map()
    all_regions = [lookup(p, 'aws.region', None) for p in all_projects.values()]
    region_list = list(set(filter(None, all_regions))) # remove any Nones, make unique, make a list
    if not region_list:
        raise EnvironmentError("no regions available at all!")
    if len(region_list) > 1:
        raise MultipleRegionsError(region_list)
    return region_list[0]

@testme
def _find_master(stacks):
    if len(stacks) == 1:
        # first item (stackname) of first (and only) result
        return first(first(stacks))

    msl = filter(lambda triple: is_master_server_stack(first(triple)), stacks)
    msl = map(first, msl) # just stack names
    if len(msl) > 1:
        LOG.warn("more than one master server found: %s. this state should only ever be temporary.", msl)
    # this all assumes master servers with YMD instance ids
    #master_server_ymd_instance_id = lambda x: ''.join(x.split('--')[2:])
    #msl = sorted(msl, key=master_server_ymd_instance_id, reverse=True)
    msl = sorted(msl, key=parse_stackname, reverse=True)
    return first(msl)

def find_master(region):
    "returns the most recent aws master-server it can find. assumes instances have YMD names"
    stacks = active_aws_stacks(region)
    if not stacks:
        raise NoMasterException("no master servers found in region %r" % region)
    return _find_master(stacks)

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
    subsubdomain = re.sub(r'[^\w\-]', '', instance_id)
    hostname = subsubdomain + "--" + subdomain

    updates = {
        'hostname': hostname,
    }

    if domain:
        updates['project_hostname'] = subdomain + "." + domain
        updates['full_hostname'] = hostname + "." + domain

    if intdomain:
        updates['int_project_hostname'] = subdomain + "." + intdomain
        updates['int_full_hostname'] = hostname + "." + intdomain

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

    return project_data

#
# might be better off in bakery.py?
#

@testme
def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (project_name_from_stackname(stackname), utils.ymd())
