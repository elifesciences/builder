import os
import time
import fabric.api as fab_api
import fabric.contrib.files as fab_files
import fabric.exceptions as fab_exceptions
import fabric.state
import fabric.network
import logging
from io import BytesIO
from . import utils, threadbare
from functools import partial

THREADBARE = 'threadbare'
FABRIC = 'fabric'

DEFAULT_BACKEND = FABRIC

BACKEND = os.environ.get('BLDR_BACKEND', DEFAULT_BACKEND)
assert BACKEND in [FABRIC, THREADBARE]

def api(fabric_fn, threadbare_fn):
    return fabric_fn if BACKEND == FABRIC else threadbare_fn

COMMAND_LOG = []

_default_env = {}
_default_env.update(fab_api.env)

def envdiff():
    "temporary. returns only the elements that are different between the default Fabric env and the env as it is right now"
    return {k: v for k, v in fab_api.env.items() if _default_env.get(k) != v}

def spy(fn):
    "temporary. wrapper to inspect inputs to commands"
    # Fabric 1.14 documentation: https://docs.fabfile.org/en/1.14/
    def _wrapper(*args, **kwargs):
        timestamp = time.time()
        funcname = getattr(fn, '__name__', '???')
        lst = [timestamp, funcname, args, kwargs]
        print(lst)
        COMMAND_LOG.append(lst)
        with open('/tmp/command-log.jsonl', 'a') as fh:
            msg = utils.json_dumps({"ts": timestamp, "fn": funcname, "args": args, "kwargs": kwargs, 'env': envdiff()}, dangerous=True)
            fh.write(msg + "\n")
        result = fn(*args, **kwargs)
        return result
    return _wrapper

def no_match(msg):
    def fn(*args, **kwargs):
        return None
    return fn

LOG = logging.getLogger(__name__)

env = api(fab_api.env, threadbare.state.ENV)

#
# exceptions
#

class CommandException(Exception):
    pass

# no un-catchable errors from Fabric
# env.abort_exception = CommandException # env is just a dictionary with attribute access

# TODO: how to handle this ...
# with initial_settings() ... ? we could explicitly go from an empty environment to default settings
#env['abort_exception'] = CommandException

NetworkError = fab_exceptions.NetworkError

#
# api
#

def fab_api_local_remote_wrapper(fab_result):
    """Fabric returns the stdout of the command when capture=True, with stderr and some values also available as attributes.
    This modifies the behaviour of Fabric's `local` to return a dictionary of results."""
    # local:
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1240-L1251
    # run/sudo:
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L971
    result = fab_result.__dict__
    result['stdout'] = (fab_result or b"").splitlines()
    result['stderr'] = (fab_result.stderr or b"").splitlines()
    return result

def fab_api_local_wrapper(*args, **kwargs):
    return fab_api_local_remote_wrapper(fab_api.local(*args, **kwargs))

def fab_api_run_wrapper(*args, **kwargs):
    return fab_api_local_remote_wrapper(fab_api.run(*args, **kwargs))

def fab_api_sudo_wrapper(*args, **kwargs):
    return fab_api_local_remote_wrapper(fab_api.sudo(*args, **kwargs))

# https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L158-L241
def fab_api_settings_wrapper(*args, **kwargs):
    "a context manager that alters mutable application state for functions called within it's scope"

    # these values were set with `fabric.state.output[key] = val`
    # they would be persistant until the program exited
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L448-L474
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        fabric.state.output[key] = val

    return fab_api.settings(*args, **kwargs)

#

local = api(fab_api_local_wrapper, threadbare.operations.local)
execute = api(fab_api.execute, partial(threadbare.execute.execute_with_hosts, env))
parallel = api(fab_api.parallel, threadbare.execute.parallel)
serial = api(fab_api.serial, threadbare.execute.serial)

hide = api(fab_api.hide, threadbare.operations.hide)

settings = api(fab_api_settings_wrapper, threadbare.state.settings)

lcd = api(fab_api.lcd, threadbare.operations.lcd) # local change dir
rcd = api(fab_api.cd, threadbare.operations.rcd) # remote change dir

remote = api(fab_api_run_wrapper, threadbare.operations.remote)
remote_sudo = api(fab_api_sudo_wrapper, threadbare.operations.remote_sudo)
upload = api(fab_api.put, threadbare.operations.upload)
download = api(fab_api.get, threadbare.operations.download)
remote_file_exists = api(fab_files.exists, threadbare.operations.remote_file_exists)

network_disconnect_all = api(fabric.network.disconnect_all,
                             no_match("threadbare automatically closes ssh closes connections"))

#
# deprecated api
# left commented out for reference
#

#cd = rcd
#put = upload
#get = download
#run = remote
#sudo = remote_sudo

#
# moved
#

# previously `buildercore.core.listfiles_remote`, renamed for consistency.
# function has very little usage
def remote_listfiles(path=None, use_sudo=False):
    """returns a list of files in a directory at `path` as absolute paths"""
    if not path:
        raise AssertionError("path to remote directory required")
    with fab_api.hide('output'):
        runfn = remote_sudo if use_sudo else remote
        path = "%s/*" % path.rstrip("/")
        result = runfn("for i in %s; do echo $i; done" % path)
        stdout = result['stdout']
        if stdout and stdout[0] == path: # some kind of bash artifact where it returns `/path/*` when no matches
            return []
        return stdout

def fab_get(remote_path, local_path=None, use_sudo=False, label=None, return_stream=False):
    "wrapper around fabric.operations.get"
    label = label or remote_path
    msg = "downloading %s" % label
    LOG.info(msg)
    local_path = local_path or BytesIO()
    download(remote_path, local_path, use_sudo=use_sudo)
    if isinstance(local_path, BytesIO):
        if return_stream:
            local_path.seek(0) # reset stream's internal pointer
            return local_path
        return local_path.getvalue().decode() # return a string
    return local_path

def fab_put(local_path, remote_path, use_sudo=False, label=None):
    "wrapper around fabric.operations.put"
    label = label or local_path
    msg = "uploading %s to %s" % (label, remote_path)
    LOG.info(msg)
    upload(local_path=local_path, remote_path=remote_path, use_sudo=use_sudo)
    return remote_path

def fab_put_data(data, remote_path, use_sudo=False):
    utils.ensure(isinstance(data, bytes) or utils.isstr(data), "data must be bytes or a string that can be encoded to bytes")
    data = data if isinstance(data, bytes) else data.encode()
    bytestream = BytesIO(data)
    label = "%s bytes" % bytestream.getbuffer().nbytes if utils.gtpy2() else "? bytes"
    return fab_put(bytestream, remote_path, use_sudo=use_sudo, label=label)
