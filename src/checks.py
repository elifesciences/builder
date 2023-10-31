from buildercore import core
from utils import TaskExit


def stack_exists(stackname, state=None):
    """Prints `True` if the stack exists, accepts `state` param.
    if `state` is 'steady', stack must not be transitioning between states.
    if `state` is 'active', stack must be in healthy state (no failed updates)."""
    if not core.stack_exists(stackname, state):
        raise TaskExit() # a log.INFO in core.describe_stacks is good enough
