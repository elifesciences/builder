from buildercore import project
from buildercore.project import stack_generation
from decorators import requires_stack_config, format_output
import utils

@format_output()
def list_stacks(include_resources=True):
    """prints the list of known stacks.
    by default also prints the stack's list of resources."""
    include_resources = utils.strtobool(include_resources)
    stack_map = project.stack_map()
    if include_resources:
        return [{stackname: [r['meta']['type'] for r in stackdata['resource-list']]} for stackname, stackdata in stack_map.items()]
    return stack_map.keys()

@format_output()
@requires_stack_config
def stack_config(stackname):
    "prints the stack configuration for the given `stackname`"
    return project.stack_map()[stackname]

def generate_stacks(resource_type, config_path):
    """generate new stacks with a single resource of the given `resource_type`.
    intended to bulk populate config files."""
    try:
        stack_generation.generate_stacks(resource_type, config_path)
    except AssertionError as ae:
        raise utils.TaskExit(ae)
