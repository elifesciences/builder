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
    "returns a list of all project names whose projects have a truthy ec2 section (eg, not {}, None or False)"
    def has_ec2(pname, pdata):
        if pdata.get('aws') and pdata['aws'].get('ec2'):
            return pname
        # if evidence of an ec2 section not found directly, check alternate configurations
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            if alt_data.get('ec2'):
                return pname
    results = [has_ec2(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results


@report
def all_ec2_instances(state=None):
    "returns a list of all ec2 instance names. set `state` to `running` to see all running ec2 instances."
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]

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
