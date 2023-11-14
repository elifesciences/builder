import utils
from buildercore import core
from decorators import format_output


@format_output('json')
def stack_list():
    """Lists active Cloudformation stacks.
    'active' stacks are in the 'created', 'updated' or
    'update rollback complete' states."""
    region = utils.find_region()
    return core.active_stack_names(region)
