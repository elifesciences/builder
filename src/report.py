from buildercore import core, project
from functools import wraps

def print_list(row_list, checkboxes=True):
    template = "- %s"
    if checkboxes:
        template = "- [ ] %s"
    for row in row_list:
        print(template % row)

def report(fn):
    @wraps(fn)
    def _wrapped(checkboxes=True, *args, **kwargs):
        results = fn(*args, **kwargs)
        print_list(results, checkboxes)
    return _wrapped
        
@report
def all_projects():
    return project.project_list()

@report
def all_ec2_projects():
    pass

@report
def all_ec2_instances():
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instances(state=None)]

@report
def all_formulas():
    pass
