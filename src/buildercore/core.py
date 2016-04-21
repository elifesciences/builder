import os, glob, json, inspect, re, copy
from os.path import join
from . import utils, config
from .utils import first, testme, dictfilter
from collections import OrderedDict
from functools import wraps
import boto
from boto.exception import BotoServerError
from contextlib import contextmanager
from fabric.api import settings

import logging

LOG = logging.getLogger(__name__)

class PredicateException(Exception):
    pass

#
# 
#

@utils.cached
def boto_cfn_conn():
    "returns a AWS CloudFormation connection"
    return boto.connect_cloudformation()

@utils.cached
def boto_ec2_conn():
    return boto.connect_ec2()

def find_ec2_instance(stackname):
    "returns ec2 instance data for a *specific* stackname"
    # filters: http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
    return boto_ec2_conn().get_only_instances(filters={'tag:Name':[stackname],
                                                       # introduced 2015-12-03
                                                       'instance-state-name': ['running']})

def find_ec2_volume_by_iid(iid):
    #http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
    return boto_ec2_conn().get_all_volumes(filters={'attachment.instance-id': iid})

def find_ec2_volume(stackname):
    ec2_data = find_ec2_instance(stackname)[0]
    return find_ec2_volume_by_iid(ec2_data.id)

def deploy_user_pem():
    return join(config.PRIVATE_DIR, 'deploy-user.pem')

@contextmanager
def stack_conn(stackname, username=config.DEPLOY_USER):
    data = stack_data(stackname)
    public_ip = data['instance']['ip_address']
    with settings(user=username, host_string=public_ip, key_filename=deploy_user_pem()):
        yield

#
# stack file wrangling
# 'stack files' are the things on the file system in the `cfn/` dir.
#

def is_master_server_stack(stackname):
    return 'master-server-' in stackname

def parse_stack_file_name(stack_filename):
    "returns just the stackname sans leading dirs and trailing extensions given a path to a stack"
    stack = os.path.basename(stack_filename) # just the file
    return os.path.splitext(stack)[0] # just the filename

# lists of stacks

def stack_files():
    "returns a list of manually created cloudformation stacknames"
    stacks = glob.glob("%s/*.json" % config.STACK_PATH)
    return map(parse_stack_file_name, stacks)


#

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

def old_stack(stackname):
    "predicate. returns True if the given stack is an 'old' stack (uses Parameters)"
    return stack_json(stackname, parse=True).has_key("Parameters")


#
# aws stack wrangling
# 'aws stacks' are stack files that have been given to AWS and provisioned.
#

# DO NOT CACHE. use sparingly
def describe_stack(stackname):
    "returns the full details of a stack given it's name or ID"
    return first(boto_cfn_conn().describe_stacks(stackname))

# TODO: rename or something
def stack_data(stackname):
    stack = describe_stack(stackname)
    data = stack.__dict__
    if data.has_key('outputs'):
        data['indexed_output'] = {row.key: row.value for row in data['outputs']}
    try:
        # TODO: is there someway to go straight to the instance ID ?
        # a CloudFormation's outputs go stale! because we can't trust the data it
        # gives us, we sometimes take it's instance-id and talk to the instance directly.
        #inst_id = data['indexed_output']['InstanceId']
        #inst = get_instance(inst_id)
        inst = find_ec2_instance(stackname)[0]
        data['instance'] = inst.__dict__
    except Exception:
        LOG.exception('caught an exception attempting to discover more information about this instance. The instance may not exist yet ...')
    return data


# DO NOT CACHE
def stack_is_active(stackname):
    "returns True if the given stack is in a completed state"
    try:
        return describe_stack(stackname).stack_status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']
    except BotoServerError as err:
        if err.message.endswith('does not exist'):
            return False
        LOG.warning("unhandled exception testing active state of stack %r", stackname)
        raise

def stack_triple(aws_stack):
    "returns a triple of (name, status, data) of stacks."
    return (aws_stack.stack_name, aws_stack.stack_status, aws_stack)

# lists of aws stacks

@utils.cached
def raw_aws_stacks():
    # I suspect the number of results returned is paginated
    status_filters = [
        #'CREATE_IN_PROGRESS',
        #'CREATE_FAILED',
        'CREATE_COMPLETE',
        #'ROLLBACK_IN_PROGRESS',
        #'ROLLBACK_FAILED',
        #'DELETE_IN_PROGRESS',
        #'DELETE_FAILED',
        #'UPDATE_IN_PROGRESS',
        #'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
        'UPDATE_COMPLETE',
        #'UPDATE_ROLLBACK_IN_PROGRESS',
        #'UPDATE_ROLLBACK_FAILED',
        #'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
        #'UPDATE_ROLLBACK_COMPLETE',
    ]
    return boto_cfn_conn().list_stacks(status_filters)

@utils.cached
def all_aws_stacks():
    "returns a stack triple of all active stacks *from the last 90 days*."
    return map(stack_triple, raw_aws_stacks())

def all_aws_stack_names():
    "convenience. returns a list of names for all active stacks AS WELL AS inactive stacks for the last 90 days"
    return sorted(map(first, all_aws_stacks()))

@utils.cached
def all_active_stacks():
    "returns all active stacks as a triple of (stackname, status, data)"
    return map(stack_triple, boto_cfn_conn().describe_stacks())

def find_master():
    "returns the most recent aws master-server it can find. assumes instances have YMD names"
    sl = all_active_stacks()
    msl = filter(lambda triple: is_master_server_stack(first(triple)), sl)
    msl = map(first, msl) # just stack names
    master_server_ymd_instance_id = lambda x: ''.join(x.split('-')[2:])
    msl = sorted(msl, key=master_server_ymd_instance_id, reverse=True)
    return first(msl)

#
# decorators
#

def _requires_fn_stack(func, pred, message=None):
    "meta decorator. returns a wrapped function that is executed if pred(stackname) is true"
    @wraps(func)
    def _wrapper(stackname=None, *args, **kwargs):
        if stackname and pred(stackname):
            return func(stackname, *args, **kwargs)
        if message:
            msg = message % {'stackname': stackname}
        else:
            msg = "\n\nfunction `%s()` failed predicate \"%s\" on stack '%s'\n" \
              % (func.__name__, str(inspect.getsource(pred)).strip(), stackname)
        raise PredicateException(msg)
    return _wrapper

def requires_active_stack(func):
    "requires a stack to exist in a successfully created/updated state"
    return _requires_fn_stack(func, stack_is_active)

def requires_stack_file(func):
    "requires a stack template to exist on disk"
    msg = "I couldn't find a cloudformation stack file for %(stackname)r!"
    return _requires_fn_stack(func, lambda stackname: stackname in stack_files(), msg)

#
#
#

def project_name_from_stackname(stackname, careful=False):
    "returns the project from the given stackname"
    # project names are sorted from longest to shortest.
    # so, if we're not being careful, "lax-nonrds" would be picked over "lax" for "lax-nonrds-develop"
    plist = sorted(project_list(), cmp=lambda v1, v2: len(v2) - len(v1))
    res = [p for p in plist if str(stackname).startswith(p + "-")]
    if careful:
        assert len(res) == 1, "more than one result returned for %s! %s" % (stackname, ", ".join(res))
    if not res:
        raise ValueError("could not find a project name from stack %r" % stackname)
    return res[0]

def normalize_stackname(stackname):
    return re.sub(r'[^\w\-]', '', stackname)

@testme
def mk_hostname(project, stackname, project_file=config.PROJECT_FILE):
    """given a project and a stackname, returns a hostname without the domain name
    for example, 'develop.lax' or 'production.crm'"""
    _, all_project_data = read_projects(project_file)
    data = all_project_data[project]
    
    subdomain = data.get('subdomain', None)
    if not subdomain:
        LOG.info("%s does not have a subdomain to create a hostname from. ignoring.", project)
        return None

    # strip the project name from the stackname
    assert stackname.startswith(project), "expected the stackname %r to start with project %r" % (stackname, project)
    instance_id = stackname[len(project) + 1:] # +1 for the hyphen

    # clean the stackname up
    instance_id = normalize_stackname(instance_id)
    
    return "%(instance_id)s.%(subdomain)s" % locals()

#
#
#

@testme
def all_projects(project_file=config.PROJECT_FILE):
    allp = utils.ordered_load(open(project_file))
    defaults = allp["defaults"]
    del allp["defaults"]
    return defaults, allp

@testme
def read_projects(project_file=config.PROJECT_FILE, env_type='aws'):
    "reads the `project_file` and returns a pair of (defaults, project data)"
    env_type_list = ["aws", "vagrant"]
    defaults, allp = all_projects(project_file)
    supported_projects = OrderedDict([(name, data[env_type]) for name, data in allp.items() if data.has_key(env_type)])
    # shifts anything not in 'aws' or 'vagrant' into the project data as top level keys
    for name, data in allp.items():
        if data.has_key(env_type):
            supported_projects[name].update(utils.exsubdict(data, env_type_list))
    return defaults, supported_projects

def filtered_projects(filterfn, *args, **kwargs):
    "returns a pair of (defaults, dict of projects filtered by given filterfn)"
    defaults, allp = read_projects(*args, **kwargs)
    return defaults, dictfilter(filterfn, allp)

def branch_deployable_projects(*args, **kwargs):
    "returns a pair of (defaults, dict of projects with a repo)"
    return filtered_projects(lambda k, v: v.has_key('repo'))

#
# new-style project data handling
#

def _merge_snippets(pname, snippets):
    snippets = [{}] + snippets # so none of the snippets are mutated
    def mergedefs(snip1, snip2):
        utils.deepmerge(snip1, snip2)
        return snip1
    overrides = reduce(mergedefs, snippets).get(pname, {})
    return overrides

def project_data(pname, project_file=config.PROJECT_FILE, snippets=0xDEADBEEF):
    "does a deep merge of defaults+project data with a few exceptions"

    if snippets == 0xDEADBEEF:
        snippets = find_snippets(project_file)
    
    # merge all snippets providing a 'defaults' key first
    default_overrides = _merge_snippets('defaults', snippets)
    
    global_defaults, project_list = all_projects(project_file)
    project_defaults = copy.deepcopy(global_defaults)
    utils.deepmerge(project_defaults, default_overrides)

    project_data = project_defaults
    
    # exceptions.
    # these values *shouldn't* be merged if they *don't* exist in the project
    excluding = ['aws', 'vagrant', 'vagrant-alt', 'aws-alt', {'aws': ['rds', 'ext']}]
    utils.deepmerge(project_data, project_list[pname], excluding)

    # handle the alternate configurations
    for altname, altdata in project_data.get('aws-alt', {}).items():
        # take project's current aws state, merge in overrides, merge over top of original aws defaults
        project_aws = copy.deepcopy(project_data['aws'])
        orig_defaults = copy.deepcopy(global_defaults['aws'])
        utils.deepmerge(project_aws, altdata)
        utils.deepmerge(orig_defaults, project_aws, ['rds', 'ext'])
        project_data['aws-alt'][altname] = orig_defaults

    for altname, altdata in project_data.get('vagrant-alt', {}).items():
        orig = copy.deepcopy(altdata)
        utils.deepmerge(altdata, project_data['vagrant'])
        utils.deepmerge(altdata, orig)

    # merge in any per-project overrides
    project_overrides = _merge_snippets(pname, snippets)
    utils.deepmerge(project_data, project_overrides)
    
    return project_data

def project_data_for_stackname(stackname, *args, **kwargs):
    pname = project_name_from_stackname(stackname, careful=True)
    return project_data(pname, *args, **kwargs)

def project_alt_config_names(pdata, env='aws'):
    "returns names of all alternate configurations for given project data and environment (default aws)"
    assert env in ['vagrant', 'aws'], "'env' must be either 'vagrant' or 'aws'"
    return pdata.get(env + '-alt', {}).keys()

def set_project_alt(pdata, env, altkey):
    "non-destructive update of given project data with the specified alternative configuration."
    assert env in ['vagrant', 'aws'], "'env' must be either 'vagrant' or 'aws'"
    env_key = env + '-alt'
    assert pdata[env_key].has_key(altkey), "project has no alternative config %r" % altkey
    pdata_copy = copy.deepcopy(pdata) # don't modify the data given to us
    pdata_copy[env] = pdata[env_key][altkey]
    return pdata_copy

def project_file_name(project_file=config.PROJECT_FILE):
    "returns the name of the project file without the extension"
    fname = os.path.splitext(project_file)[0]
    return os.path.basename(fname)

def project_dir_path(project_file=config.PROJECT_FILE):
    # /path/to/elife-builder/project/elife.yaml =>
    # /path/to/elife-builder/project/elife/
    path = join(os.path.dirname(project_file), project_file_name(project_file))
    if not os.path.exists(path):
        os.mkdir(path)
    return path

def write_project_data(pname, project_file=config.PROJECT_FILE, *args, **kwargs):
    data = project_data(pname, *args, **kwargs)
    path = join(project_dir_path(project_file), pname + ".json")
    json.dump(data, open(path, 'w'), indent=4)
    return path

def find_snippets(project_file=config.PROJECT_FILE):
    path = project_dir_path(project_file)
    path_list = map(lambda fname: join(path, fname), os.listdir(path))
    path_list = filter(os.path.isfile, path_list)
    path_list = filter(lambda p: p.endswith('.yaml'), path_list)
    path_list.sort() # your snippets need to be in a natural ordering
    return map(lambda p: utils.ordered_load(open(p, 'r')), path_list)


#
#
#

@testme
def project_list(project_file=config.PROJECT_FILE):
    "returns a list of known project names from the given project file, excluding 'defaults'"
    _, all_projects = read_projects(project_file)
    return all_projects.keys()

@testme
def update_project_file(path, value, project_data=None, project_file=config.PROJECT_FILE):
    if not project_data:
        project_data = utils.ordered_load(open(project_file, 'r'))
    utils.updatein(project_data, path, value, create=True)
    return project_data

@testme
def write_project_file(new_project_data, project_file=config.PROJECT_FILE):
    data = utils.ordered_dump(new_project_data)
    # this awful bit of code injects two new lines after before each top level element
    lines = []
    for line in data.split('\n'):
        if line and lines and line[0] != " ":
            lines.append("")
            lines.append("")
        lines.append(line)
    # all done. convert back to ordereddict
    #new_project_data = utils.ordered_load(StringIO("\n".join(lines)))
    open(project_file, 'w').write("\n".join(lines)) #utils.ordered_dump(new_project_data))
    return project_file

@testme
def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (project_name_from_stackname(stackname), utils.ymd())
