from buildercore import config as core_config
from buildercore.project import stack_config
from decorators import requires_project_stack, echo_output
import utils

def list(include_resources=True):
    """prints the list of known stacks.
    by default also prints the stack's list of resources."""
    include_resources = utils.strtobool(include_resources)
    stack_map = stack_config.all_stack_data(core_config.TEMP_PROJECT_STACK_CONFIG)
    for stackname, stackdata in stack_map.items():
        print(stackname)
        if include_resources:
            for resource in stackdata['resource-list']:
                print("    -", resource['meta']['type'])

@echo_output
@requires_project_stack
def config(stackname):
    "prints the stack configuration for the given `stackname`"
    return stack_config.stack_data(stackname, core_config.TEMP_PROJECT_STACK_CONFIG)
