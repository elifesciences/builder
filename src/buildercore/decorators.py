from functools import wraps
import logging

LOG = logging.getLogger(__name__)

def ossissue(issue):
    def wrap1(func):
        @wraps(func)
        def wrap2(*args, **kwargs):
            LOG.warn("TODO: " + issue)
            return func(*args, **kwargs)
        return wrap2
    return wrap1
