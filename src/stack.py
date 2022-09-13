from buildercore import project
from decorators import requires_stack_config, echo_output
import utils

@echo_output
def list(include_resources=True):
    """prints the list of known stacks.
    by default also prints the stack's list of resources."""
    include_resources = utils.strtobool(include_resources)
    stack_map = project.stack_map()
    if include_resources:
        return [{stackname: [r['meta']['type'] for r in stackdata['resource-list']]} for stackname, stackdata in stack_map.items()]
    return stack_map.keys()

@echo_output
@requires_stack_config
def config(stackname):
    "prints the stack configuration for the given `stackname`"
    return project.stack_map()[stackname]
