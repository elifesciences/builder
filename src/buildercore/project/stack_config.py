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
from deepmerge import Merger

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
    "returns true if the stack data (or 'defaults' data) has a non-nil 'path' property under 'meta'"
    return bool(utils.lookup(data, 'meta.path', None))

def read_stack_file(path):
    "reads the contents of the YAML file at `path`."
    data = utils.yaml_load_2(open(path, 'r'))
    # elaborate to check before `parse_stack_map` is called to insert a reference to where this data originated.
    # this is necessary so we know where to update a stack in future.
    # it also means we can't rely on this value being present if we're not parsing stack data from a file.
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
    # bit of a hack, but prune the 'meta.path' value if it exists.
    # this might be part of a larger pattern of post-processing in future
    for toplevel, stack in data.items():
        if stack_has_path(stack):
            del stack['meta']['path']
    return utils.yaml_dumps_2(data)

def write_stack_file(data, path):
    open(path, 'w').write(_dumps_stack_file(data))

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
        resource_name, resource_data = list(resource.items())[0]
        resource_defaults = utils.deepcopy(stack_defaults["resource-map"][resource_name])
        return {resource_name: deep_merge(resource_defaults, resource_data)}

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
