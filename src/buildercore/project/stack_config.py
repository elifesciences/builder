"""
'stack' configuration deals with *extant* infrastructure - stuff that is out there in the world.

In contrast to 'project' configuration (./projects/elife.yaml) which is a template based.

Template-based project configuration already muddies the water between 'just a template' and actual infrastructure,
which is why we have 'unique' alt-configs that can't be used like a template at all (see `journal--prod` or anything
that is `unique: true`).

Once an instance of a project is created it can be added to the stack config (or not) and managed that way.

2022-09-09: some notes to guide me

stack config is a means to:
* bring existing infrastructure under configuration control.
* create new infrastructure.
* destroy existing infrastructure.
* *document* and assign *responsibility* of infrastructure.
* *group* disparate bits of infrastructure.

stack configuration is *not*:
- intended to replace 'project' configuration.
- particularly deep or complex, it should be a thin wrapper around CFN and TForm to begin with

"""

from buildercore import utils
from buildercore.utils import ensure

# https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries/7205107#answer-24088493
def deep_merge(d1, d2):
    """Update two dicts of dicts recursively,
    if either mapping has leaves that are non-dicts,
    the second's leaf overwrites the first's.

    non-destructive."""
    for k, v in d1.items():
        if k in d2:
            if all(isinstance(e, dict) for e in (v, d2[k])):
                d2[k] = deep_merge(v, d2[k])
            # further type checks and merge as appropriate here.
            # ...
    d3 = d1.copy()
    d3.update(d2)
    return d3

# ---

def read_stacks_file(path):
    "reads the contents of the YAML file at `path`."
    return utils.yaml_load(open(path, 'r'))

def parse_stacks_data(stacks_data):
    "returns a pair of `(stack-defaults, map-of-stackname-to-stackdata)`"
    if stacks_data is None:
        return ({}, {})
    ensure(isinstance(stacks_data, dict), "stacks data must be a dictionary, not type %r" % type(stacks_data))
    ensure("defaults" in stacks_data, "stacks data missing a `default` section: %s" % stacks_data.keys())
    ensure("resource-map" in stacks_data["defaults"], "defaults section is missing a `resource-map` field: %s" % list(stacks_data.keys()))
    defaults = stacks_data.pop("defaults")
    return defaults, stacks_data

def _stack_data(stack_defaults, stack_data):
    sd = deep_merge(stack_defaults, stack_data)

    def deep_merge_resource(resource):
        resource_name, resource_data = list(resource.items())[0]
        return deep_merge(stack_defaults["resource-map"][resource_name], resource_data)

    sd['resource-list'] = [deep_merge_resource(r) for r in sd['resource-list']]
    del sd['resource-map']
    return sd

def all_stacks_data(path):
    stacks_data = read_stacks_file(path)
    stack_defaults, stack_list = parse_stacks_data(stacks_data)
    return {stackname: _stack_data(stack_defaults, stack_data) for stackname, stack_data in stack_list.items()}
