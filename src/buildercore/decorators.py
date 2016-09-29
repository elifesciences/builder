import json, inspect
from functools import wraps
from . import config
import logging

LOG = logging.getLogger(__name__)

class FeatureDisabledException(Exception):
    pass

class PredicateException(Exception):
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
        raise PredicateException(msg)
    return _wrapper

def if_enabled(key, silent=False):
    def wrap1(func):
        @wraps(func)
        def wrap2(*args, **kwargs):
            settings = config.app()
            assert settings.has_key(key), "no setting with value %r" % key
            enabled = settings[key]
            assert isinstance(enabled, bool), "expecting the value at %r to be a boolean" % key
            if enabled:
                return func(*args, **kwargs)
            if silent:
                LOG.info("feature %r is disabled, returning silently", key)
                return None
            msg = "the feature %r is disabled. you can enable it with \"%s: True\" in your `settings.yml` file" % (key, key)
            raise FeatureDisabledException(msg)
        return wrap2
    return wrap1    

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
