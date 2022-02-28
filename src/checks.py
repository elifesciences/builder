from buildercore import core
from utils import TaskExit

def stack_exists(stackname, state=None):
    """returns `True` if the stack exists.
    if `state` is 'steady', stack must also be in a non-transitioning 'steady' state.
    if `state` is 'active', stack must also be in a healthy 'active' state (no failed updates, etc)."""
    if not core.stack_exists(stackname, state):
        raise TaskExit() # a log.INFO in core.describe_stacks is good enough
