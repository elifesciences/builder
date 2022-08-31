from time import time
import os
from os.path import join
import utils
from buildercore import core, project, config, cloudformation
from buildercore.utils import first, remove_ordereddict, errcho, lfilter, lmap, isstr, ensure
from functools import wraps
from pprint import pformat
import logging

LOG = logging.getLogger(__name__)


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

def requires_filtered_project(filterfn=None):
    def wrap1(func):
        @wraps(func)
        def wrap2(_pname=None, *args, **kwargs):
            pname = config.ENV['PROJECT'] or _pname # used by Vagrant ...?
            project_list = project.filtered_projects(filterfn)
            if not pname or not pname.strip() or pname not in project_list:
                # TODO:
                # if config.BUILDER_NON_INTERACTIVE:
                #    print('project name not found or not provided and input is disabled, cannot continue.')
                #    return
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
        def _wrapper(stackname=None, *args, **kwargs):
            region = utils.find_region(stackname)
            asl = core.active_stack_names(region)
            if not asl:
                print('\nno AWS stacks exist, cannot continue.')
                return

            def pname_startswith(stack):
                for pname in plist:
                    if stack.startswith(pname):
                        return stack
            asl = lfilter(pname_startswith, asl)
            if not stackname or stackname not in asl:
                stackname = utils._pick("stack", asl)
            return func(stackname, *args, **kwargs)
        return _wrapper
    return wrap1

def requires_aws_stack(func):
    """requires a stack to exist and will prompt if one was not provided."""
    @wraps(func)
    def call(*args, **kwargs):
        stackname = first(args) or config.ENV['INSTANCE']
        region = utils.find_region(stackname)
        if stackname:
            args = args[1:]
            return func(stackname, *args, **kwargs)
        # note: this assumes all stacks have an ec2 instance.
        asl = core.active_stack_names(region)
        if not asl:
            raise RuntimeError('\nno AWS stacks *in an active state* exist, cannot continue.')
        if not stackname or stackname not in asl:
            stackname = utils._pick("stack", asl, default_file=deffile('.active-stack'))
        args = args[1:]
        return func(stackname, *args, **kwargs)
    return call

def requires_aws_stack_template(func):
    """downloads the cloudformation JSON template and writes it to disk before calling wrapped function.
    assumes first argument to task is a `stackname`."""
    @wraps(func)
    def call(stackname, *args, **kwargs):
        stack_template_path = cloudformation.find_template_path(stackname)
        msg = "task requires cloudformation template to exist locally, but template not found and could not be downloaded: " + stack_template_path
        ensure(os.path.exists(stack_template_path), msg, utils.TaskExit)
        return func(stackname, *args, **kwargs)
    return call

def requires_steady_stack(func):
    @wraps(func)
    def call(*args, **kwargs):
        ss = core.steady_aws_stacks(utils.find_region())
        keys = lmap(first, ss)
        idx = dict(zip(keys, ss))
        helpfn = lambda pick: idx[pick][1]
        if not keys:
            print('\nno AWS stacks *in a steady state* exist, cannot continue.')
            return
        stackname = first(args) or config.ENV['INSTANCE']
        if not stackname or stackname not in keys:
            stackname = utils._pick("stack", sorted(keys), helpfn=helpfn, default_file=deffile('.active-stack'))
        return func(stackname, *args[1:], **kwargs)
    return call

def echo_output(func):
    "pretty-prints the return value of the task(s) being run to stdout"
    @wraps(func)
    def _wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        errcho('output:') # printing to stderr avoids corrupting structured data
        if isstr(res):
            print(res)
        else:
            print(pformat(remove_ordereddict(res)))
        return res
    return _wrapper
