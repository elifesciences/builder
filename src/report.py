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

def report(task_fn):
    "wraps a task, printing it's results as a sorted list to `stdout`."
    @wraps(task_fn)
    def _wrapped(checkboxes=True, ordered=True, *args, **kwargs):
        ordered = utils.strtobool(ordered)
        checkboxes = utils.strtobool(checkboxes)
        results = task_fn(*args, **kwargs)
        if not results:
            return
        if ordered:
            results = sorted(results, key=sort_by_env)
        print_list(results, checkboxes)
        return results
    return _wrapped

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
        "master-server--2018-04-09-2--1", # updated in separate step
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
    def adhoc_instance(stackname):
        "predicate, returns True if stackname is *not* in a known environment"
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
