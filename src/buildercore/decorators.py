from functools import wraps
import logging

LOG = logging.getLogger(__name__)

def osissuefn(issue):
    LOG.warn("TODO: " + issue)

def osissue(issue):
    def wrap1(func):
        @wraps(func)
        def wrap2(*args, **kwargs):
            osissuefn(issue)
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
