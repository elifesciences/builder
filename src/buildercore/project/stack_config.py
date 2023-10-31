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

from deepmerge import Merger

from buildercore import utils
from buildercore.utils import ensure


def deep_merge(d1, d2):
    custom_merger = Merger(
        [(list, ["override"]),
         (dict, ["merge"]),
         (set, ["union"])],
        # fallback strategies applied to all other types
        ["override"],
        # strategies in the case where the types conflict
        ["override"]
    )
    return custom_merger.merge(d1, d2)

# ---

def stack_has_path(data):
    "returns `True` if the given stack `data` (or 'defaults' data) has a non-nil 'path' property under 'meta'"
    return isinstance(data, dict) and bool(utils.lookup(data, 'meta.path', None))

def read_stack_file(path):
    "reads the contents of the YAML file at `path`, returning Python data."
    with open(path) as fh:
        data = utils.ruamel_load(fh)
    # a check before `parse_stack_map` to insert a reference to where this data originated.
    # it's necessary so we know where to update an individual stack in future during stack regeneration.
    # the 'defaults.meta.type' path is simply to test that `meta` is a dict.
    if bool(utils.lookup(data, 'defaults.meta.type', None)):
        data['defaults']['meta']['path'] = path
    return data

def parse_stack_map(stack_map):
    "returns a pair of `(stack-defaults, map-of-stackname-to-stackdata)`"
    if stack_map is None:
        return ({}, {})
    ensure(isinstance(stack_map, dict), "stack data must be a dictionary, not type %r" % type(stack_map))
    ensure("defaults" in stack_map, "stack data missing a `default` section: %s" % stack_map.keys())
    ensure("resource-map" in stack_map["defaults"], "defaults section is missing a `resource-map` field: %s" % list(stack_map.keys()))
    defaults = stack_map.pop("defaults")
    return defaults, stack_map

def _dumps_stack_file(data):
    """processes the given stack data and then returns a YAML string.
    any 'meta.path' values are removed, stack keys are ordered, 'defaults' must be present."""
    ensure(isinstance(data, dict), "expecting a dictionary")
    ensure('defaults' in data, "no 'defaults' section found")

    def prune_path(toplevel, data):
        if stack_has_path(data):
            del data['meta']['path']
        return data
    data = utils.dictmap(prune_path, data)

    order = ['name', 'description', 'meta']
    order = dict(zip(order, range(0, len(order)))) # {'id': 0, 'name': 1, ...}

    def order_keys(toplevel, data):
        if toplevel == 'defaults':
            return data
        return {key: data[key] for key in sorted(data, key=lambda n: order.get(n) or 99)}
    # this destroys comments as it replaces the ruamel.ordereddict with a regular dict.
    # comments for 'defaults' can be guaranteed but not for resources.
    data = utils.dictmap(order_keys, data)

    return utils.ruamel_dumps(data)

def write_stack_file(data, path):
    "same as `_dumps_stack_file`, but the result is written to `path`"
    with open(path, 'w') as fh:
        fh.write(_dumps_stack_file(data))

def write_stack_file_updates(data, path):
    "reads stack config, replacing the stack configuration with `data` and writes the changes back to file."
    # todo: how to ignore default values?
    # for example, `data` may contain values present in the definition of the stack that don't need to be present.
    # we need a sort of deep-merge-set-exclusion where deeply identical values are removed instead of ignored
    stack_map = read_stack_file(path)
    new_stack_map = deep_merge(stack_map, data)
    write_stack_file(new_stack_map, path)

def _stack_data(stack_defaults, raw_stack_data):
    """merges the `stack_defaults` dict with the abbreviated `raw_stack_data` dict resulting in a 'full' stack.
    each resource in `resource-list` is merged with it's definition in `resource-map`.
    `resource-map` definitions are subject to deep-merge as well prior to resource-list being filled out,
    so it's possible (but not recommended) for you to add or override a per-stack resource definition.
    `resource-map` definitions are stripped off before being returned.
    behaves very similarly to project-config."""
    stack_defaults = utils.deepcopy(stack_defaults)
    sd = deep_merge(stack_defaults, raw_stack_data)

    def deep_merge_resource(resource):
        resource_type = resource['meta']['type']
        resource_defaults = utils.deepcopy(stack_defaults["resource-map"][resource_type])
        return deep_merge(resource_defaults, resource)

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
