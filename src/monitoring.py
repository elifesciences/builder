import functools
from fabric.api import task as original_task
import newrelic.agent

def task(*args, **kwargs):
    invoked = bool(not args or kwargs)
    if not invoked:
        func, args = args[0], ()

    def wrapper(func):
        @functools.wraps(func)
        def monitored(*args, **kwargs):
            application = newrelic.agent.register_application(timeout=1.0)
            #print func.func_name
            with newrelic.agent.BackgroundTask(application, name='example_short_startup_timeout'):
                return func(*args, **kwargs)

        return original_task(monitored, *args, **kwargs)

    return wrapper if invoked else wrapper(func)

