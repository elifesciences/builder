import os
import fabric.api as fab_api
import fabric.contrib.files as fab_files
import fabric.exceptions as fab_exceptions
import fabric.state
import fabric.network
import logging
from io import BytesIO
from . import utils, threadbare

THREADBARE = 'threadbare'
FABRIC = 'fabric'

#DEFAULT_BACKEND = THREADBARE
DEFAULT_BACKEND = FABRIC

BACKEND = os.environ.get('BLDR_BACKEND', DEFAULT_BACKEND)
assert BACKEND in [FABRIC, THREADBARE]

def api(fabric_fn, threadbare_fn):
    "accepts two functions and returns the one matching the currently set BACKEND"
    return fabric_fn if BACKEND == FABRIC else threadbare_fn

def no_op(msg):
    "used in rare circumstances when either a function in Fabric or Threadbare doesn't have a corollary in the other"
    def fn(*args, **kwargs):
        return None
    return fn

LOG = logging.getLogger(__name__)

#
# exceptions
#

class CommandException(Exception):
    pass

if BACKEND == FABRIC:
    # no un-catchable errors from Fabric
    fab_api.env['abort_exception'] = CommandException
else:
    threadbare.state.set_defaults({"abort_exception": CommandException,
                                   "key_filename": os.path.expanduser("~/.ssh/id_rsa")})

NetworkError = fab_exceptions.NetworkError

#
# api
#

# local:
# - https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L1240-L1251
# run/sudo:
# - https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L898-L971
def fab_api_results_wrapper(fab_fn):
    """Fabric returns the stdout of the command when capture=True, with stderr and some values also available as attributes.
    This modifies the behaviour of Fabric's `local`, `run` and `sudo` commands to return a dictionary of results."""
    def wrapper(*args, **kwargs):
        fab_result = fab_fn(*args, **kwargs)
        result = fab_result.__dict__
        result['stdout'] = (fab_result or b"").splitlines()
        result['stderr'] = (fab_result.stderr or b"").splitlines()
        return result
    return wrapper

# settings:
# - https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L158-L241
def fab_api_settings_wrapper(*args, **kwargs):
    "a context manager that alters mutable application state for functions called within it's scope"

    # these values were set with `fabric.state.output[key] = val`
    # they would be persistant until the program exited
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L448-L474
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        fabric.state.output[key] = val

    return fab_api.settings(*args, **kwargs)

def threadbare_state_settings_wrapper(*args, **kwargs):
    utils.ensure(not args, "threadbare doesn't support non-keyword arguments.")
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        opt = f"display_{key}" # display_running, display_prefix, display_aborts, etc
        kwargs[opt] = val
    return threadbare.state.settings(*args, **kwargs)

#

# lsh@2020-12-10: last minute change to how `env` is accessed.
# worker processes during multiprocessing seem to hang on to old imported references of `env`.
# this means `buildercore.command.env` is missing values, but `buildercore.threadbare.state.ENV` is fine.
# force proper reference by enclosing in a function.
#env = api(fab_api.env, threadbare.state.ENV)
def env(key=None):
    """function for accessing the globally shared and mutable 'env' dictionary.
    When called without a `key` it returns the whole dictionary."""
    _env = api(fab_api.env, threadbare.state.ENV)
    return _env[key] if key is not None else _env

local = api(fab_api_results_wrapper(fab_api.local), threadbare.operations.local)
execute = api(fab_api.execute, threadbare.execute.execute_with_hosts)
parallel = api(fab_api.parallel, threadbare.execute.parallel)
serial = api(fab_api.serial, threadbare.execute.serial)

hide = api(fab_api.hide, threadbare.operations.hide)

settings = api(fab_api_settings_wrapper, threadbare_state_settings_wrapper)

lcd = api(fab_api.lcd, threadbare.operations.lcd) # local change dir
rcd = api(fab_api.cd, threadbare.operations.rcd) # remote change dir

remote = api(fab_api_results_wrapper(fab_api.run), threadbare.operations.remote)
remote_sudo = api(fab_api_results_wrapper(fab_api.sudo), threadbare.operations.remote_sudo)
upload = api(fab_api.put, threadbare.operations.upload)
download = api(fab_api.get, threadbare.operations.download)
remote_file_exists = api(fab_files.exists, threadbare.operations.remote_file_exists)

network_disconnect_all = api(fabric.network.disconnect_all,
                             no_op("threadbare automatically closes ssh closes connections"))

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
