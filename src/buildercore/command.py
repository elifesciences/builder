import os
import logging
import threadbare
from io import BytesIO
from . import utils

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

NetworkError = threadbare.operations.NetworkError
threadbare.state.set_defaults({"abort_exception": CommandException,
                               "key_filename": os.path.expanduser("~/.ssh/id_rsa")})

#
# api
#

def threadbare_state_settings_wrapper(**kwargs):
    """a context manager that alters mutable application state for functions called within it's scope.
    Not necessary for threadbare but there are some outlier Fabric settings that need coercing."""
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        opt = "display_" + key # display_running, display_aborts, etc
        kwargs[opt] = val
    if 'output_prefix' in kwargs:
        kwargs['display_prefix'] = kwargs.pop('output_prefix')
    return threadbare.state.settings(**kwargs)

# lsh@2020-12-10: worker processes during multiprocessing seem to hang on to old imported references of `env`.
# this means `buildercore.command.env` is missing values but `buildercore.threadbare.state.ENV` is fine.
# force proper reference by enclosing in a function.
def env(key=None):
    """function for accessing the globally shared and mutable 'env' dictionary.
    When called without a `key` it returns the whole dictionary."""
    _env = threadbare.state.ENV
    return _env[key] if key is not None else _env

local = threadbare.operations.local
execute = threadbare.execute.execute_with_hosts
parallel = threadbare.execute.parallel
serial = threadbare.execute.serial

hide = threadbare.operations.hide

settings = threadbare_state_settings_wrapper

lcd = threadbare.operations.lcd # local change dir
rcd = threadbare.operations.rcd # remote change dir

remote = threadbare.operations.remote
remote_sudo = threadbare.operations.remote_sudo
upload = threadbare.operations.upload
download = threadbare.operations.download
remote_file_exists = threadbare.operations.remote_file_exists

#
# moved
#

# TODO: consider pushing into threadbare
def remote_listfiles(path=None, use_sudo=False):
    """returns a list of files in a directory at `path` as absolute paths"""
    if not path:
        raise AssertionError("path to remote directory required")
    runfn = remote_sudo if use_sudo else remote
    path = "%s/*" % path.rstrip("/")
    result = runfn("for i in %s; do echo $i; done" % path)
    stdout = result['stdout']
    if stdout and stdout[0] == path: # some kind of bash artifact where it returns `/path/*` when no matches
        return []
    return stdout

# TODO: rename, update docstr
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

# TODO: rename, update docstr
def fab_put(local_path, remote_path, use_sudo=False, label=None):
    "wrapper around fabric.operations.put"
    label = label or local_path
    msg = "uploading %s to %s" % (label, remote_path)
    LOG.info(msg)
    upload(local_path=local_path, remote_path=remote_path, use_sudo=use_sudo)
    return remote_path

# TODO: rename, docstr
def fab_put_data(data, remote_path, use_sudo=False):
    utils.ensure(isinstance(data, bytes) or utils.isstr(data), "data must be bytes or a string that can be encoded to bytes")
    data = data if isinstance(data, bytes) else data.encode()
    bytestream = BytesIO(data)
    label = "%s bytes" % bytestream.getbuffer().nbytes
    return fab_put(bytestream, remote_path, use_sudo=use_sudo, label=label)
