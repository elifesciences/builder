import inspect
import json
import logging
from functools import wraps

LOG = logging.getLogger(__name__)

class PredicateError(Exception):
    pass

def _requires_fn_stack(func, pred, message=None):
    "meta decorator. returns a wrapped function that is executed if pred(stackname) is true"
    @wraps(func)
    def _wrapper(stackname=None, *args, **kwargs):
        if stackname and pred(stackname):
            return func(stackname, *args, **kwargs)
        if message:
            msg = message % {'stackname': stackname}
        else:
            msg = "\n\nfunction `%s()` failed predicate \"%s\" on stack '%s'\n" \
                % (func.__name__, str(inspect.getsource(pred)).strip(), stackname)
        raise PredicateError(msg)
    return _wrapper

def spy(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        LOG.info("func %r called with args %r and kwargs %r", fn.__name__, args, kwargs)
        retval = fn(*args, **kwargs)
        LOG.info("func %r returned with value:\n%s", fn.__name__, json.dumps(retval, indent=4))
        return retval
    return wrapper
