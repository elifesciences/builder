import utils
from buildercore import project
from buildercore.project import stack_generation
from decorators import format_output, requires_stack_config


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
    except AssertionError as err:
        raise utils.TaskExit(err) from err

def regenerate_stack(stackname):
    "updates all resources for the given `stackname`."
    stack = stack_config(stackname)
    config_path = stack['meta']['path']
    print('this file may be modified:', config_path)
    stack_generation.regenerate(stackname, config_path)
