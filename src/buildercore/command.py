import os
import threadbare
from io import BytesIO
from . import utils, config
import logging

LOG = logging.getLogger(__name__)

#
# exceptions
#

class CommandException(Exception):
    pass

NetworkError = threadbare.operations.NetworkError
threadbare.state.set_defaults({"abort_exception": CommandException,
                               "key_filename": os.path.expanduser(config.USER_PRIVATE_KEY)})

#
# api
#

# lsh@2020-12-10: worker processes during multiprocessing seem to hang on to old imported references of `env`.
# this means `buildercore.command.env` is missing values but `buildercore.threadbare.state.ENV` is fine.
# force proper reference by enclosing within a function.
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

settings = threadbare.state.settings

lcd = threadbare.operations.lcd # local change dir
rcd = threadbare.operations.rcd # remote change dir

remote = threadbare.operations.remote
remote_sudo = threadbare.operations.remote_sudo
upload = threadbare.operations.upload
download = threadbare.operations.download
remote_file_exists = threadbare.operations.remote_file_exists

#
# wrappers/convenience functions
#

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

def get(remote_path, local_path=None, use_sudo=False, label=None, return_stream=False):
    """downloads the file at `remote_path` to `local_path` that may be a bytes buffer.
    if `local_path` is a bytes buffer and `return_stream` is `False` (default), the buffer is filled, closed and the result is returned.
    if `local_path` is a bytes buffer and `return_stream` is `True`, the buffer is filled and it's pointer reset before returning."""
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

def put(local_path, remote_path, use_sudo=False, label=None):
    "convenience wrapper around `threadbare.upload` that uploads the file at `local_path` to `remote_path`."
    label = label or local_path
    msg = "uploading %s to %s" % (label, remote_path)
    LOG.info(msg)
    upload(local_path=local_path, remote_path=remote_path, use_sudo=use_sudo)
    return remote_path

def put_data(data, remote_path, use_sudo=False):
    "convenience wrapper around `command.put` that uploads `data` as if it were a file to `remote_path`."
    utils.ensure(isinstance(data, bytes) or utils.isstr(data), "data must be bytes or a string that can be encoded to bytes")
    data = data if isinstance(data, bytes) else data.encode()
    bytestream = BytesIO(data)
    label = "%s bytes" % bytestream.getbuffer().nbytes
    return put(bytestream, remote_path, use_sudo=use_sudo, label=label)
