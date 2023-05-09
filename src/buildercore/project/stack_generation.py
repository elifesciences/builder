'''logic to generate and refresh the configuration of stacks and their list of resources.

'''
from functools import reduce
import os
from buildercore.utils import ensure, merge
from buildercore.project import stack_config, stack_generation__s3_bucket

import logging

LOG = logging.getLogger(__name__)

def _regenerate_resource(resource):
    "updates the given `resource`."
    dispatch = {
        's3-bucket': stack_generation__s3_bucket.regenerate_resource,
    }
    dispatch_fn = dispatch[resource['meta']['type']]
    return dispatch_fn(resource)

def regenerate(stackname, config_path):
    """update each of the resources for the given `stackname` in stack config file `config_path`."""
    stack_map = stack_config.read_stack_file(config_path)
    defaults, stack_map = stack_config.parse_stack_map(stack_map)
    ensure(stackname in stack_map, "stack %r not found. known stacks: %s" % (stackname, ", ".join(stack_map.keys())))
    stack = stack_map[stackname]

    new_resource_list = [_regenerate_resource(resource) for resource in stack['resource-list']]
    stack['resource-list'] = new_resource_list
    stack_config.write_stack_file_updates({stackname: stack}, config_path)

# ---

def generate_stacks(resource_type, config_path):
    """generate new stacks with a single resource of the given `resource_type`.
    intended to bulk populate config files.
    does *not* remove stacks that were previously generated but have since been deleted."""
    dispatch = {
        's3-bucket': stack_generation__s3_bucket.generate_stack
    }
    ensure(resource_type in dispatch,
           "unsupported resource type %r. supported resource types: %s" % (resource_type, ", ".join(dispatch.keys())))
    ensure(os.path.exists(config_path), "config path %r does not exist" % config_path)

    dispatch_fn = dispatch[resource_type]
    generated_stack_list = dispatch_fn(config_path)

    # sanity check, make sure each generated stack looks like:
    # {"foo-bucket": {"name": "foo-bucket", "meta": {...}, ...}}
    for stack in generated_stack_list:
        ensure(len(stack.keys()) == 1, "bad stack, expected exactly 1 key: %r" % stack)

    stack_map = reduce(merge, generated_stack_list)
    stack_config.write_stack_file_updates(stack_map, config_path)
