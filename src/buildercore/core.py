"""this module appears to be where I collect functionality 
that is built upon by the more specialised parts of builder.

suggestions for a better name than 'core' welcome."""

import os, glob, json, re
from os.path import join
from . import utils, config, project # BE SUPER CAREFUL OF CIRCULAR DEPENDENCIES
from .decorators import testme
import decorators
from .utils import first, lookup
from boto.exception import BotoServerError
from contextlib import contextmanager
from fabric.api import settings, execute
import importlib
import logging
from kids.cache import cache as cached
from slugify import slugify

LOG = logging.getLogger(__name__)

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
def connect_aws_with_pname(pname, service):
    "convenience"
    pdata = project.project_data(pname)
    region = pdata['aws']['region']
    print 'connecting to a',pname,'instance in region',region
    return connect_aws(service, region)

def connect_aws_with_stack(stackname, service):
    "convenience"
    pname = project_name_from_stackname(stackname)
    return connect_aws_with_pname(pname, service)

def find_ec2_instance(stackname):
    "returns list of ec2 instances data for a *specific* stackname"
    # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
    filter_by_cluster = {
        'tag-key': ['Cluster', 'Name'],
        'tag-value': [stackname],
        'instance-state-name': ['running'],
    }
    conn = connect_aws_with_stack(stackname, 'ec2')
    return conn.get_only_instances(filters=filter_by_cluster)

def find_ec2_volume(stackname):
    ec2_data = find_ec2_instance(stackname)[0]
    iid = ec2_data.id
    #http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
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
    public_ip = data['instance']['ip_address']
    params = _ec2_connection_params(stackname, username, host_string=public_ip)

    with settings(**params):
        yield

def stack_all_ec2_nodes(stackname, work, username=config.DEPLOY_USER, **kwargs):
    """Executes work on all the EC2 nodes of stackname.    
    Optionally connects with the specified username or with additional settings
    from kwargs"""
    public_ips = [ec2['instance']['ip_address'] for ec2 in stack_data(stackname)]
    params = _ec2_connection_params(stackname, username)

    with settings(**params):
        # TODO: decorate work to print what it is connecting only
        execute(work, hosts=public_ips)
    



#
# stackname wrangling
#    

def mk_stackname(*bits):
    return "--".join(map(slugify, filter(None, bits)))

#TODO: test these functions
def parse_stackname(stackname, all_bits=False):
    "returns a pair of (project, instance-id) by default, optionally returns the cluster id if all_bits=True"
    if not stackname or not isinstance(stackname, basestring):
        raise ValueError("stackname must look like <pname>--<instance-id>[--<cluster-id>], got: %r" % str(stackname))
    # https://docs.python.org/2/library/stdtypes.html#str.split
    bits = stackname.split('--',  -1 if all_bits else 1)
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
    """like `describe_stack`, but returns a dictionary with the Cloudformation 'outputs' 
    indexed by key and ec2 data under the key 'instance'
    
    Returns a list if more than one result is found, but otherwise sticks
    to a single dictionary for backward compatibility"""
    stack = describe_stack(stackname)
    try:
        # TODO: is there someway to go straight to the instance ID ?
        # a CloudFormation's outputs go stale! because we can't trust the data it
        # gives us, we sometimes take it's instance-id and talk to the instance directly.
        ec2_instances = find_ec2_instance(stackname)

        assert len(ec2_instances) >= 1, ("found no ec2 instances for %r" % stackname)
        if ensure_single_instance:
            raise RuntimeError("talking to multiple EC2 instances is not supported for this task yet: %r" % stackname)

        def do(ec2):
            data = stack.__dict__
            data['instance'] = ec2.__dict__
            return data
        return map(do, ec2_instances)

    except Exception:
        LOG.exception('caught an exception attempting to discover more information about this instance. The instance may not exist yet ...')


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
    stacks= active_aws_stacks(region)
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

def project_data_for_stackname(stackname, *args, **kwargs):
    pname = project_name_from_stackname(stackname)
    return project.project_data(pname, *args, **kwargs)

#
# might be better off in bakery.py?
#

@testme
def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (project_name_from_stackname(stackname), utils.ymd())
