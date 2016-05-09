import json
from functools import wraps
import logging

LOG = logging.getLogger(__name__)

def osissuefn(issue):
    LOG.warn("TODO: " + issue)

def osissue(issue):
    def wrap1(func):
        aissue = "`%s` %s" % (func.__name__, issue)
        @wraps(func)
        def wrap2(*args, **kwargs):
            osissuefn(aissue)
            return func(*args, **kwargs)
        return wrap2
    return wrap1

def testme(fn):
    "a wrapper that emits an annoying message when a function is testable"
    @wraps(fn)
    def wrapper(*args, **kwargs):
        LOG.debug("%s is VERY testable ...", fn.__name__)
        return fn(*args, **kwargs)
    return wrapper

def spy(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        LOG.info("func %r called with args %r and kwargs %r", fn.__name__, args, kwargs)
        retval = fn(*args, **kwargs)
        LOG.info("func %r returned with value:\n%s", fn.__name__, json.dumps(retval, indent=4))
        return retval
    return wrapper
