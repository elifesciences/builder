"""`stack.py` is the interface to the new resource description and wrangling logic.

`stackcore/*.py` is where all of the non-interface stack wrangling logic lives.

This separation is to reduce any further complexity in `buildercore/*` which is entirely
orientated around the current resource description and data structures.

"""


from stackcore import project
from stackcore.project import stack_generation
from decorators import format_output, requires_stack_config
import utils

@format_output()
def list_stacks(include_resources=True):
    """prints the list of known stacks.
    by default also prints the stack's list of resources."""
    include_resources = utils.strtobool(include_resources)
    stack_map = project.stack_map()
    if include_resources:
        retval = []
        for stackname, stackdata in stack_map.items():
            retval.append({stackname: [r['meta']['type'] for r in stackdata['resource-list']]})
        return retval
    return list(stack_map.keys())

@format_output()
@requires_stack_config
def stack_config(stackname):
    "prints the stack configuration for the given `stackname`"
    # return project.stack_map()[stackname] # naive but not as slow as you might think.
    return project.stack(stackname)

def generate_stacks(resource_type, config_path):
    """generate new stacks with a single resource of the given `resource_type`.
    intended to bulk populate config files."""
    try:
        stack_generation.generate_stacks(resource_type, config_path)
    except AssertionError as ae:
        raise utils.TaskExit(ae)

def regenerate_stack(stackname):
    "updates all resources for the given `stackname`."
    stack = stack_config(stackname)
    config_path = stack['meta']['path']
    print('this file may be modified:', config_path)
    stack_generation.regenerate(stackname, config_path)
