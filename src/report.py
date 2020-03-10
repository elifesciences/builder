import os
import utils
from buildercore import core, project, utils as core_utils
from functools import wraps

def print_list(row_list, checkboxes=True):
    "given a list of things, prints a markdown list to stdout with optional checkboxes"
    template = "- %s"
    if checkboxes:
        template = "- [ ] %s"
    for row in row_list:
        print(template % row)

def report(fn):
    "wraps a task, printing it's results as a sorted list to stdout"
    @wraps(fn)
    def _wrapped(checkboxes=True, ordered=True, *args, **kwargs):
        ordered = utils.strtobool(ordered)
        checkboxes = utils.strtobool(checkboxes)
        results = fn(*args, **kwargs)
        if not results:
            return
        # TODO: this could be better. ci first, continuumtest next, etc
        if ordered:
            results.sort()
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
    formula_url_list = filter(None, list(set(core_utils.shallow_flatten(project.project_formulas().values()))))
    formula_list = map(lambda url: os.path.basename(url), formula_url_list)
    return formula_list

@report
def all_ec2_projects():
    "return a list of all project names whose projects have a truthy ec2 section (eg, not {}, None or False)"
    def has_ec2(pname, pdata):
        if pdata.get('aws') and pdata['aws'].get('ec2'):
            return pname
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            if alt_data.get('ec2'):
                return pname
    results = [has_ec2(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results


@report
def all_ec2_instances(state=None):
    "all ec2 instances. set `state` to `running` to see all running ec2 instances"
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]

@report
def all_adhoc_ec2_instances(state='running'):
    "all ec2 instances whose instance ID doesn't match a known environment"

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
        "predicate, returns True if stackname is in a known environment"
        try:
            iid = core.parse_stackname(stackname, all_bits=True, idx=True)['instance_id']
            return iid not in env_list
        except (ValueError, AssertionError):
            # thrown by `parse_stackname` when given value isn't a string or
            # delimiter not found in string.
            return True
    instance_list = [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]
    return filter(adhoc_instance, instance_list)
