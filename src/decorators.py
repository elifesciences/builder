import os
from os.path import join
import utils
from buildercore import core, project, config
from buildercore.utils import first, remove_ordereddict, errcho
from functools import wraps
from fabric.api import env, task
from pprint import pformat
import logging

LOG = logging.getLogger(__name__)

from time import time

# http://stackoverflow.com/questions/1622943/timeit-versus-timing-decorator
def timeit(fn):
    @wraps(fn)
    def wrap(*args, **kw):
        ts = time()
        result = fn(*args, **kw)
        te = time()
        LOG.info('func:%r args:[%r, %r] took: %2.4f sec',
                 fn.__name__, args, kw, te - ts)
        return result
    return wrap

def deffile(fname):
    "returns the proper path to the given default file"
    return join(config.TEMP_PATH, fname)

def setdefault(fname, value):
    "writes the given value to the given default file"
    open(deffile(fname), 'w').write(value)

def rtask(*roles):
    "role task. this task is only available for certain roles specified in the BLDR_ROLE env var"
    def wrapper(func):
        role_env = os.getenv('BLDR_ROLE')
        if role_env in roles:
            # a role has been set
            return task(func)
        return func
    return wrapper


# pylint: disable=invalid-name
debugtask = rtask('admin')
mastertask = rtask('master')

def requires_filtered_project(filterfn=None):
    def wrap1(func):
        @wraps(func)
        def wrap2(_pname=None, *args, **kwargs):
            pname = os.environ.get('PROJECT', _pname)
            project_list = project.filtered_projects(filterfn)
            if not pname or not pname.strip() or pname not in project_list:
                pname = utils._pick("project", sorted(project_list), default_file=deffile('.project'))
            return func(pname, *args, **kwargs)
        return wrap2
    return wrap1


# pylint: disable=invalid-name
requires_project = requires_filtered_project(None)

def requires_aws_project_stack(*plist):
    if not plist:
        plist = [utils._pick("project", project.project_list(), default_file=deffile('.project'))]

    def wrap1(func):
        @wraps(func)
        def _wrapper(stackname, *args, **kwargs):
            stackname = stackname or os.environ.get('INSTANCE')
            region = aws.find_region(stackname)
            if not stackname:
                asl = core.active_stack_names(region)
                if not asl:
                    print '\nno AWS stacks exist, cannot continue.'
                    return

                def pname_startswith(stack):
                    for pname in plist:
                        if stack.startswith(pname):
                            return stack
                asl = filter(pname_startswith, asl)
                if not stackname or stackname not in asl:
                    stackname = utils._pick("stack", asl, default_file=deffile('.active-stack'))
            res = func(stackname, *args, **kwargs)
            setdefault('.active-stack', stackname)
            return res
        return _wrapper
    return wrap1

def requires_aws_stack(func):
    @wraps(func)
    def call(*args, **kwargs):
        stackname = first(args) or os.environ.get('INSTANCE')
        region = aws.find_region(stackname)
        if stackname:
            args = args[1:]
            return func(stackname, *args, **kwargs)
        asl = core.active_stack_names(region)
        if not asl:
            raise RuntimeError('\nno AWS stacks *in an active state* exist, cannot continue.')
        if not stackname or stackname not in asl:
            stackname = utils._pick("stack", asl, default_file=deffile('.active-stack'))
        args = args[1:]
        return func(stackname, *args, **kwargs)
    return call

def requires_steady_stack(func):
    @wraps(func)
    def call(*args, **kwargs):
        ss = core.steady_aws_stacks(aws.find_region())
        keys = map(first, ss)
        idx = dict(zip(keys, ss))
        helpfn = lambda pick: idx[pick][1]
        if not keys:
            print '\nno AWS stacks *in a steady state* exist, cannot continue.'
            return
        stackname = first(args) or os.environ.get('INSTANCE')
        if not stackname or stackname not in keys:
            stackname = utils._pick("stack", sorted(keys), helpfn=helpfn, default_file=deffile('.active-stack'))
        return func(stackname, *args[1:], **kwargs)
    return call

def requires_feature(key, silent=False):
    "very similar to `buildercore.if_required` but fails gently"
    def wrap1(func):
        @wraps(func)
        def wrap2(*args, **kwargs):
            if config.feature_enabled(key):
                return func(*args, **kwargs)
            print
            print "feature %r is disabled." % key
            print "you can enable it with \"%s: True\" in your `settings.yml` file" % key
            print
            exit(1)
        return wrap2
    return wrap1

def _sole_task(nom):
    task_list = env.tasks
    if len(task_list) > 0:
        final_task = task_list[-1]
        final_task = final_task.split(':', 1)[0] # ignore any args
        final_task = final_task.split('.')[-1] # handles namespaced tasks like: webserver.vhost
        return final_task == nom

def echo_output(func):
    """if the wrapped function is the sole task being run, then it's output is
    printed to stdout. this wrapper first attempts to pass the keyword
    'verbose' to the function and, if it fails, calls it without.
    """
    @wraps(func)
    def _wrapper(*args, **kwargs):
        if _sole_task(func.__name__):
            res = func(*args, **kwargs)
            errcho('output:') # printing to stderr avoids corrupting structured data
            if isinstance(res, str) or isinstance(res, unicode):
                print res
            else:
                print pformat(remove_ordereddict(res))
            return res
        return func(*args, **kwargs)
    return _wrapper


# avoid circular dependencies.
# TODO: this is a design smell. refactor.
import aws
