import os
from os.path import join
import utils
from buildercore import core
from buildercore.utils import first
from functools import wraps
from fabric.api import env, task
from pprint import pformat

LOG = logging.getLogger(__name__)

def deffile(fname):
    "returns the proper path to the given default file"
    return join(core.project_dir_path(), fname)

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

#pylint: disable=invalid-name
debugtask = rtask('debug')

def requires_filtered_project(filterfn=None):
    def wrap1(func):
        @wraps(func)
        def wrap2(project=None, *args, **kwargs):
            project = os.environ.get('PROJECT', project)
            if not project or not project.strip():
                _, project_list = core.filtered_projects(filterfn)
                project = utils._pick("project", sorted(project_list), default_file=deffile('.project'))
            return func(project, *args, **kwargs)
        return wrap2
    return wrap1

#pylint: disable=invalid-name
requires_branch_deployable_project = requires_filtered_project(lambda pname, project: project.has_key('repo'))
#pylint: disable=invalid-name
requires_project = requires_filtered_project(None)

def requires_aws_project_stack(*plist):
    if not plist:
        plist = [utils._pick("project", core.project_list(), default_file=deffile('.project'))]
    def wrap1(func):
        @wraps(func)
        def _wrapper(stackname=None, *args, **kwargs):
            asl = core.all_aws_stack_names()
            if not asl:
                print '\nno AWS stacks exist, cannot continue.'
                return
            def pname_startswith(stack):
                for pname in plist:
                    if stack.startswith(pname):
                        return stack
            asl = filter(pname_startswith, asl)
            if not stackname or stackname not in asl:
                stackname = utils._pick("stack", asl)
            return func(stackname, *args, **kwargs)
        return _wrapper
    return wrap1

def requires_aws_stack(func):
    @wraps(func)
    def call(*args, **kwargs):
        asl = core.all_aws_stack_names()
        stackname = first(args)
        if not asl:
            print '\nno AWS stacks exist, cannot continue.'
            return
        if not stackname or stackname not in asl:
            stackname = utils._pick("stack", asl, default_file=deffile('.active-stack'))
        else:
            args = args[1:]
        return func(stackname, *args, **kwargs)
    return call

def _sole_task(nom):
    task_list = env.tasks
    if len(task_list) > 0:
        final_task = task_list[-1]
        final_task = final_task.split('.')[-1] # handles namespaced tasks like: webserver.vhost
        return final_task.split(':')[0] == nom     # remove any args given to the function

def echo_output(func):
    """if the wrapped function is the sole task being run, then it's output is
    printed to stdout. this wrapper first attempts to pass the keyword
    'verbose' to the function and, if it fails, calls it without.
    """
    @wraps(func)
    def _wrapper(*args, **kwargs):
        if _sole_task(func.__name__):
            res = func(*args, **kwargs)
            print 'output:\n'
            if isinstance(res, str) or isinstance(res, unicode):
                print res
            else:
                print pformat(res)
            return res
        return func(*args, **kwargs)
    return _wrapper
