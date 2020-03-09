import os
from buildercore import core, project, utils as core_utils
from functools import wraps

def print_list(row_list, checkboxes=True):
    template = "- %s"
    if checkboxes:
        template = "- [ ] %s"
    for row in row_list:
        print(template % row)

def report(fn):
    @wraps(fn)
    def _wrapped(checkboxes=True, ordered=True, *args, **kwargs):
        results = fn(*args, **kwargs)
        if not results:
            return
        # TODO: this could be better. ci first, continuumtest next, etc
        if ordered:
            results.sort()
        print_list(results, checkboxes)
    return _wrapped
        
@report
def all_projects():
    "a list of *all* projects"
    return project.project_list()

@report
def all_formulas():
    "returns a list of all known formulas"
    formula_url_list = filter(None, list(set(core_utils.shallow_flatten(project.project_formulas().values()))))
    formula_list = map(lambda url: os.path.basename(url), formula_url_list)
    return formula_list

@report
def all_ec2_projects():
    "all projects that use ec2"
    pass

@report
def all_ec2_instances(state=None):
    "all ec2 instances. set `state` to `running` to see all running ec2 instances"
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instances(state=state)]

def all_adhoc_ec2_instances():
    "all ec2 instances whose instance ID doesn't match a known environment"
    return all_ec2_instances(state='running')
    
