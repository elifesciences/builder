import copy
from multiprocessing import Process, Queue
import time
from .common import first
from . import state


# https://github.com/mathiasertl/fabric/blob/master/fabric/decorators.py#L148-L161
def serial(func, pool_size=None):
    """Forces the given function to run `pool_size` times.
    when pool_size is None (default), executor decides how many instances of `func` to execute (1, probably).
    if set and executor is given a set of values to use instead, `pool_size` is ignored"""

    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    inner.pool_size = pool_size
    return inner


# https://github.com/mathiasertl/fabric/blob/master/fabric/decorators.py#L164-L194
def parallel(func, pool_size=None):
    """Forces the wrapped function to run in parallel, instead of sequentially."""
    wrapped_func = serial(func, pool_size)
    # `func` *must* be forced to run in parallel to main process
    wrapped_func.parallel = True
    return wrapped_func


def _parallel_execution_worker_wrapper(env, worker_func, name, queue):
    """this function is executed in another process. it wraps the given `worker_func`, initialising the `state.ENV` of
    the new process and adds its results to the given `queue`"""
    try:
        assert isinstance(env, dict), "given environment must be a dictionary"

        # Fabric nukes the child process's `env` dictionary
        # - https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L229-L237

        # note: not possible to service stdin when multiprocessing
        env["abort_on_prompts"] = True

        # we don't care what the parent process had when Python copied across it's state to
        # execute this `worker_func` in parallel. reset it now. the process is destroyed upon leaving.

        state.DEPTH = 0
        state.set_defaults(env)

        result = worker_func()
        queue.put({"name": name, "result": result})
    except BaseException as unhandled_exception:
        # kept for debugging
        # import traceback
        # traceback.print_exc()

        # "Note that exit handlers and finally clauses, etc., will not be executed."
        # - https://docs.python.org/2/library/multiprocessing.html#multiprocessing.Process.terminate
        queue.put({"name": name, "result": unhandled_exception})


def process_status(running_p):
    # https://docs.python.org/2/library/multiprocessing.html#process-and-exceptions
    result = {
        "pid": running_p.pid,
        "name": running_p.name,
        "exitcode": running_p.exitcode,
        "alive": running_p.is_alive(),
        "killed": False,
        "kill-signal": None,
    }
    if running_p.exitcode is not None and running_p.exitcode < 0:
        result["killed"] = True
        result["kill-signal"] = -running_p.exitcode
    return result


def _parallel_execution(env, func, param_key, param_values, return_process_pool=False):
    "executes the given function in parallel to main process. blocks until processes are complete"
    results_q = Queue()
    kwargs = {
        #'env': ..., # each process will get a new state dictionary
        "worker_func": func,
        #'name': ..., # a name is assigned on process start
        "queue": results_q,
    }
    pool_size = getattr(func, "pool_size", None)
    pool_size = pool_size if pool_size is not None else 1
    pool_values = param_values or range(0, pool_size)

    pool = []
    for idx, nth_val in enumerate(pool_values):
        kwargs["name"] = "process--" + str(idx + 1)  # process--1, process--2
        new_env = {} if not env else copy.deepcopy(env)

        # ssh clients are not shared between processes
        if "ssh_client" in new_env:
            del new_env["ssh_client"]

        if param_key:
            new_env[param_key] = nth_val

        new_env["parallel"] = True
        # https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L223-L227
        # new_env['linewise'] = True # not set until needed

        kwargs["env"] = new_env
        p = Process(
            name=kwargs["name"],
            target=_parallel_execution_worker_wrapper,
            kwargs=kwargs,
        )
        p.start()
        pool.append(p)

    if return_process_pool:
        # don't poll for results, don't wait to finish, just return the list of running processes
        return results_q, pool

    result_map = {}  # {process-name: process-results, ...}

    # poll the processes until all are complete
    # remove process from pool when it is complete
    while len(pool) > 0:
        for idx, running_p in enumerate(pool):
            result = process_status(running_p)
            if not result["alive"]:
                result_map[result["name"]] = result
                del pool[idx]
        # introduces the slightest of delays so that we're not manically polling every microsecond
        time.sleep(0.1)

    # all processes are complete
    # empty the queue and marry the results to their process results using their 'name'

    while not results_q.empty():
        job_result = results_q.get()
        job_name = job_result["name"]
        result_map[job_name]["result"] = job_result["result"]

    results_q.close()

    # sort the results, drop the process name
    return [b for a, b in sorted(result_map.items(), key=first)]


def _serial_execution(func, param_key, param_values):
    "executes the given function serially"
    result_list = []
    if param_key and param_values:
        for x in param_values:
            with state.settings(**{param_key: x}):
                result_list.append(func())
    else:
        # pretty boring :(
        # I could set '_idx' or something in `state.ENV` I suppose ..
        for _ in range(0, getattr(func, "pool_size", 1)):
            result_list.append(func())
    return result_list


def execute(func, param_key=None, param_values=None):
    """inspects a given function and then executes it either serially or in another process using Python's `multiprocessing` module.
    `param` and `param_list` control the number of processes spawned and the name of the parameter passed to the function.

    For example:

        execute(somefunc, param_key='host', param_values=['127.0.0.1', '127.0.1.1', 'localhost'])

    will ensure that `somefunc` has the (local) state property 'host' with a value of one of the above when executed.

    `param` and `param_list` are optional, but if one is specified then so must the other.

    parent process blocks until all child processes have completed.
    returns a map of execution data with the return values of the individual executions available under 'result'"""

    # in Fabric, `execute` is a guard-type function that ensures the function and the function's environment is
    # correct before passing it to `_execute` that does the actual magic.
    # `execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L372-L401
    # `_execute`: https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L213-L277

    # Fabric's custom 'JobQueue' adds complexity but can be avoided:
    # https://github.com/mathiasertl/fabric/blob/master/fabric/job_queue.py

    if (param_key and param_values is None) or (param_key is None and param_values):
        raise ValueError(
            "either a `param_key` AND `param_values` are provided OR neither are provided"
        )

    if param_values is not None and type(param_values) not in [list, tuple, set]:
        raise ValueError(
            "given value for `param_values` must be an iterable type, not %r"
            % type(param_values)
        )

    if param_key is not None and not isinstance(param_key, str):
        raise ValueError(
            "given value for `param_key` must be a valid function parameter key"
        )

    if hasattr(func, "parallel") and func.parallel:
        result_list = _parallel_execution(state.ENV, func, param_key, param_values)
        return [result["result"] for result in result_list]
    return _serial_execution(func, param_key, param_values)


def execute_with_hosts(func, hosts=None, line_template=None):
    """convenience wrapper around `execute`. calls `execute` on given `func` for each host in `hosts`.
    The host is available within the worker function's `env` as `host_string`."""
    host_list = hosts or state.ENV.get("hosts") or []
    assert isinstance(host_list, list), "hosts must be a list"
    # Fabric may know about many hosts ('all_hosts') but only be acting upon a subset of them ('hosts')
    # - https://github.com/mathiasertl/fabric/blob/master/sites/docs/usage/env.rst#all_hosts
    # set here:
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/tasks.py#L352
    # in elife/builder we use a map of host information:
    # - https://github.com/elifesciences/builder/blob/master/src/buildercore/core.py#L326-L327
    # - https://github.com/elifesciences/builder/blob/master/src/buildercore/core.py#L386
    # it says 'for informational purposes only' and nothing we use depends on it, so I'm disabling for now
    # env['all_hosts'] = env['hosts']
    default = "{host:15} {pipe}: {line}\n"
    line_template = line_template or state.ENV.get("line_template") or default
    with state.settings(line_template=line_template):
        results = execute(func, param_key="host_string", param_values=host_list)
    # results are ordered so we can do this
    return dict(zip(host_list, results))  # {'192.168.0.1': [], '192.169.0.3': []}
