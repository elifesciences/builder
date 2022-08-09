from functools import partial
from datetime import datetime, timezone, timedelta
import os
import utils
from buildercore import core, project, utils as core_utils
from functools import wraps

def print_list(row_list, checkboxes=True):
    "given a list of things, prints a markdown list to `stdout` with optional checkboxes."
    template = "- %s"
    if checkboxes:
        template = "- [ ] %s"
    for row in row_list:
        print(template % row)

def print_data(data, output_format='json'):
    output_format_map = {
        'json': partial(core_utils.json_dumps, dangerous=True, indent=4),
        'yaml': core_utils.yaml_dumps,
    }
    core_utils.ensure(output_format in output_format_map, "unsupported output format %r" % output_format)
    print(output_format_map[output_format](data))

def sort_by_env(name):
    """comparator. used when sorting a list of ec2 or cloudformation names.
    basic alphabetical ordering if given `name` cannot be parsed."""
    adhoc = 0 # adhoc/unrecognised names first
    order = {
        'continuumtest': 1,
        'staging': 1,
        'ci': 2,
        'end2end': 3,
        'prod': 4, # prod last
    }
    try:
        pname, env, node = core.parse_stackname(name, all_bits=True)
        # groups results by project name, then a consistent ordering by env, then node
        return "%s%s%s" % (pname, order.get(env, adhoc), node)

    except (ValueError, AssertionError):
        # thrown by `parse_stackname` when given value isn't a string or
        # delimiter not found in string.
        # by returning the given `name` here we get a basic alphabetical order
        # for lists that don't contain an environment.

        # last ditch effort for things like RDS instance names.
        for env in order:
            pos = name.find("-" + env)
            if pos > -1:
                env = name[pos + 1:] # "elife-libero-reviewer-prod" => "prod"
                rest = name[:pos] # "elife-libero-reviewer-prod" => "elife-libero-reviewer"
                key = "%s%s" % (rest, order.get(env, adhoc)) # "elife-libero-reviewer4"
                return key

        return name

def print_report(results, as_list=True, checkboxes=True, ordered=True, *args, **kwargs):
    ordered = utils.strtobool(ordered)
    checkboxes = utils.strtobool(checkboxes)
    as_list = utils.strtobool(as_list)
    if not results:
        return
    # only sort the results if we have a non-empty list of strings
    if isinstance(results, list) and results and isinstance(results[0], str) and ordered:
        results = sorted(results, key=sort_by_env)
    if as_list:
        print_list(results, checkboxes)
    else:
        print_data(results)

def report(task_fn):
    "wraps a task, printing it's results as a sorted list to `stdout`."
    @wraps(task_fn)
    def _wrapped(as_list=True, checkboxes=True, ordered=True, *args, **kwargs):
        results = task_fn(*args, **kwargs)
        print_report(results, as_list, checkboxes, ordered, *args, **kwargs)
        return results
    return _wrapped

def configured_report(**kwargs):
    "just like `report`, but you can pre-configure output options"
    def _wrap1(task_fn):
        @wraps(task_fn)
        def _wrap2(*report_args, **report_kwargs):
            results = task_fn(*report_args, **report_kwargs)
            print_report(results, **kwargs)
            return results
        return _wrap2
    return _wrap1

# ---

@report
def all_projects():
    "returns a list of all project names"
    return project.project_list()

@report
def all_formulas():
    "returns a list of all known formulas"
    # `project` will give us a map of `project-name: formula-list`
    formula_list = project.project_formulas().values()
    # flatten the list of lists into a single unique list
    formula_list = set(core_utils.shallow_flatten(formula_list))
    # remove any empty values, probably from reading the `defaults` section
    formula_list = filter(None, formula_list)
    # extract just the name from the formula url
    formula_list = map(os.path.basename, formula_list)
    return formula_list

@report
def all_ec2_projects():
    "returns a list of all project names that are using EC2 (excluding alt-configs defined in the defaults sections)"
    alt_black_list = ['fresh', 'snsalt', 's1804', '1804', '2004', 's2004', 'standalone']

    def has_ec2(pname, pdata):
        if core_utils.lookup(pdata, 'aws.ec2', None):
            return pname
        # if evidence of an ec2 section not found directly, check alternate configurations
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            if alt_name in alt_black_list:
                continue
            # we wrap in 'aws' here because we're looking for 'aws.ec2', not the un-nested 'ec2'
            if has_ec2(pname, {'aws': alt_data}):
                return pname
    results = [has_ec2(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results

def _all_ec2_instances(state):
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]

@report
def all_ec2_instances(state=None):
    "returns a list of all ec2 instance names. set `state` to `running` to see all running ec2 instances."
    return _all_ec2_instances(state)

@report
def all_ec2_instances_for_salt_upgrade():
    "returns a list of all ec2 instance names suitable for the Salt upgrade"
    ignore_these = [
        "Elife ALM (alm.svr.*)", # so very dead
        "basebox--1804--1", # ami creation, periodically destroyed and recreated
        "master-server--prod--1", # updated in separate step
        "containers-jenkins-plugin", # there are three of these
        "kubernetes-aws--flux-prod",
        "kubernetes-aws--flux-test",
        "kubernetes-aws--test",
    ]
    return [i for i in _all_ec2_instances(state=None) if i not in ignore_these]

@report
def all_adhoc_ec2_instances(state='running'):
    "returns a list of all ec2 instance names whose instance ID doesn't match a known environment"

    # extract a list of environment names from the project data
    def known_environments(pdata):
        "returns the names of all alt-config names for given project data"
        return list(pdata.get('aws-alt', {}).keys())
    env_list = core_utils.shallow_flatten(map(known_environments, project.project_map().values()))

    # append known good environments and ensure there are no dupes
    fixed_env_list = ['prod', 'end2end', 'continuumtest', 'ci', 'preview', 'continuumtestpreview']
    env_list += fixed_env_list
    env_list = list(set(filter(None, env_list)))

    # extract the names of ec2 instances that are not part of any known environment
    def adhoc_instance(ec2_name):
        "predicate, returns True if stackname is *not* in a known environment"
        stackname = ec2_name # not always true, but close enough
        try:
            iid = core.parse_stackname(stackname, all_bits=True, idx=True)['instance_id']
            return iid not in env_list
        except (ValueError, AssertionError):
            # thrown by `parse_stackname` when given value isn't a string or
            # delimiter not found in string.
            return True
    instance_list = [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]
    return filter(adhoc_instance, instance_list)

@report
def all_rds_projects():
    "returns a list of all project names that are using RDS"
    key = 'aws.rds'

    def has_(pname, pdata):
        if core_utils.lookup(pdata, key, None):
            return pname
        # if evidence of a 'foo' section not found directly, check alternate configurations
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            # we wrap in 'aws' here because we're looking for 'aws.foo', not the un-nested 'foo'
            if has_(pname, {'aws': alt_data}):
                return pname
    results = [has_(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results

@report
def all_rds_instances(**kwargs):
    """returns a list of all RDS instances.
    results are sorted by environment where possible."""
    return [i['DBInstanceIdentifier'] for i in core.find_all_rds_instances()]

@configured_report(as_list=False)
def long_running_large_ec2_instances(**kwargs):
    """returns a list of all ec2 instances that are large (> t3.medium) and that have been running for a long time."""
    #open('/tmp/output.json', 'w').write(core_utils.json_dumps(core.ec2_instance_list(state=None), dangerous=True))
    #result_list = json.load(open('/tmp/output.json', 'r'))

    result_list = core.ec2_instance_list(state='running')

    known_instance_types = {
        't3.nano': 0,
        't3.micro': 1,
        't3.small': 2,
        't3.medium': 3,
        't3.large': 4,
        't3.xlarge': 5,
        't3.2xlarge': 6
    }

    large_inst = 't3.large'

    known_env_list = [
        'ci', 'end2end', 'continuumtest', 'prod',
        'flux-test', 'flux-prod'
    ]

    long_running_duration = 4 # hrs

    # large or unknown
    def is_large_instance(result):
        inst_type = result['InstanceType']
        if inst_type not in known_instance_types:
            return result
        if known_instance_types[inst_type] >= known_instance_types[large_inst]:
            return result

    def is_long_running(result):
        launch_time = result['LaunchTime']
        if isinstance(launch_time, str):
            launch_time = datetime.fromisoformat(launch_time)
        now = datetime.now(timezone.utc)
        return (now - launch_time) > timedelta(hours=long_running_duration)

    def known_env(result):
        return core_utils.lookup(result, 'TagsDict.Environment', None) in known_env_list

    comp = lambda result: is_large_instance(result) and is_long_running(result) and not known_env(result)

    large_instances = list(filter(comp, result_list))

    def result_item(result):
        key_list = ['TagsDict.Name', 'LaunchTime', 'InstanceId', 'InstanceType', 'State.Name']
        return {key: core_utils.lookup(result, key, None) for key in key_list}

    return list(map(result_item, large_instances))
