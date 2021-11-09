from buildercore import core
from utils import strtobool, TaskExit

def stack_exists(stackname, steady=False, healthy=False):
    """returns `True` if the stack exists.
    if `healthy` is `True`, stack must also be in a healthy 'active' state (no failed updates, etc).
    if `steady` is `True`, stack must also be in a non-transitioning 'steady' state."""
    if not core.stack_exists(stackname, strtobool(steady), strtobool(healthy)):
        raise TaskExit() # a log.INFO in core.describe_stacks is good enough
