from buildercore import core
from utils import strtobool, TaskExit

def stack_exists(stackname, steady=False, healthy=False):
    """returns True if the stack exists and is a 'steady' state - not transitioning between states.
    if `healthy` is `True`, stack must also be in a healthy 'active' state (no failed updates, etc).
    if `steady` is `True`, stack must also be in a non-transitioning 'steady' state."""
    if not core.stack_exists(stackname, strtobool(steady), strtobool(healthy)):
        raise TaskExit() # INFO in core.describe_stacks is good enough
