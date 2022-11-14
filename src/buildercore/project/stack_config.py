"""
'stack' configuration deals with *extant* infrastructure - stuff that is out there in the world.

In contrast to 'project' configuration (./projects/elife.yaml) which is template based.

Template-based project configuration already muddies the water between 'just a template' and actual infrastructure,
which is why we have 'unique' alt-configs that can't be used like a template at all (see `journal--prod` or any alt-config
that is marked with `unique: true`).

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

def read_stack_file(path):
    "reads the contents of the YAML file at `path`."
    return utils.yaml_load(open(path, 'r'))

def parse_stack_map(stack_map):
    "returns a pair of `(stack-defaults, map-of-stackname-to-stackdata)`"
    if stack_map is None:
        return ({}, {})
    ensure(isinstance(stack_map, dict), "stack data must be a dictionary, not type %r" % type(stack_map))
    ensure("defaults" in stack_map, "stack data missing a `default` section: %s" % stack_map.keys())
    ensure("resource-map" in stack_map["defaults"], "defaults section is missing a `resource-map` field: %s" % list(stack_map.keys()))
    defaults = stack_map.pop("defaults")
    return defaults, stack_map

def _stack_data(stack_defaults, raw_stack_data):
    """merges the `stack_defaults` dict with the abbreviated `raw_stack_data` dict resulting in a 'full' stack.
    each resource in `resource-list` is merged with it's definition in `resource-map`.
    `resource-map` definitions are subject to deep-merge as well prior to resource-list being filled out,
    so it's possible (but not recommended) for you to add or override a per-stack resource definition.
    `resource-map` definitions are stripped off before being returned.
    behaves very similarly to project-config."""
    sd = deep_merge(stack_defaults, raw_stack_data)

    def deep_merge_resource(resource):
        resource_name, resource_data = list(resource.items())[0]
        return deep_merge(stack_defaults["resource-map"][resource_name], resource_data)

    sd['resource-list'] = [deep_merge_resource(r) for r in sd['resource-list']]
    del sd['resource-map']
    return sd

# ---

def stack_data(stackname, path):
    "convenience. reads and processes the data for a single stack at the given `path`."
    stack_map = read_stack_file(path)
    stack_defaults, stack_map = parse_stack_map(stack_map)
    return _stack_data(stack_defaults, stack_map.get(stackname, {}))

def all_stack_data(path):
    "reads and processes the data for all stacks at the given `path`."
    stack_map = read_stack_file(path)
    stack_defaults, stack_map = parse_stack_map(stack_map)
    return {stackname: _stack_data(stack_defaults, stack_data) for stackname, stack_data in stack_map.items()}
