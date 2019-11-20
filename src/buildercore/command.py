# Fabric 1.14 documentation: https://docs.fabfile.org/en/1.14/

import time
import fabric.api as fab_api
import fabric.contrib.files as fab_files
import fabric.exceptions as fab_exceptions
import fabric.state
import fabric.network
import logging
from io import BytesIO
from . import utils
import threadbare.operations
import threadbare.state
import threadbare.execute
from functools import partial
COMMAND_LOG = []

_default_env = {}
_default_env.update(fab_api.env)

def envdiff():
    "temporary. returns only the elements that are different between the default Fabric env and the env as it is right now"
    return {k: v for k, v in fab_api.env.items() if _default_env.get(k) != v}

def spy(fn):
    "temporary. wrapper to inspect inputs to commands"
    def _wrapper(*args, **kwargs):
        timestamp = time.time()
        funcname = getattr(fn, '__name__', '???')
        lst = [timestamp, funcname, args, kwargs]
        print(lst)
        COMMAND_LOG.append(lst)
        with open('/tmp/command-log.jsonl', 'a') as fh:
            msg = utils.json_dumps({"ts": timestamp, "fn": funcname, "args":args, "kwargs":kwargs, 'env': envdiff()}, dangerous=True)
            fh.write(msg + "\n")
        result = fn(*args, **kwargs)
        return result
    return _wrapper

LOG = logging.getLogger(__name__)

#env = fab_api.env
env = threadbare.state.ENV

#
# exceptions
#

class CommandException(Exception):
    pass

# no un-catchable errors from Fabric
#env.abort_exception = CommandException
env['abort_exception'] = CommandException # env is just a dictionary with attribute access

NetworkError = fab_exceptions.NetworkError

#
# api
#

local = spy(fab_api.local)
#execute = spy(fab_api.execute)
execute = partial(spy(threadbare.execute.execute_with_hosts), env)

#parallel = spy(fab_api.parallel)
parallel = spy(threadbare.execute.parallel)
#serial = spy(fab_api.serial)
serial = spy(threadbare.execute.serial)
hide = spy(fab_api.hide)

# https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L158-L241
'''
def settings(*args, **kwargs):
    "a context manager that alters mutable application state for functions called within it's scope"

    # these values were set with `fabric.state.output[key] = val`
    # they would be persistant until the program exited
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L448-L474
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        fabric.state.output[key] = val

    return spy(fab_api.settings)(*args, **kwargs)
'''
settings = spy(threadbare.state.settings)

lcd = spy(fab_api.lcd) # local change dir
rcd = spy(fab_api.cd) # remote change dir

#remote = spy(fab_api.run)
remote = spy(threadbare.operations.remote)
#remote_sudo = spy(fab_api.sudo)
remote_sudo = spy(threadbare.operations.remote_sudo)
upload = spy(fab_api.put)
download = spy(fab_api.get)
remote_file_exists = spy(fab_files.exists)
network_disconnect_all = spy(fabric.network.disconnect_all)

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
    with spy(fab_api.hide)('output'):
        runfn = remote_sudo if use_sudo else remote
        path = "%s/*" % path.rstrip("/")
        stdout = runfn("for i in %s; do echo $i; done" % path)
        if stdout == path: # some kind of bash artifact where it returns `/path/*` when no matches
            return []
        return stdout.splitlines()

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
