# Fabric 1.14 documentation: https://docs.fabfile.org/en/1.14/

import sys
import fabric.api as fab_api
import fabric.contrib.files as fab_files
import fabric.exceptions as fab_exceptions
import fabric.state
import logging
from io import BytesIO
from . import utils

LOG = logging.getLogger(__name__)

env = fab_api.env

#
# exceptions
#

class CommandException(Exception):
    pass

# lsh@2019-10: deprecated in favour of CommandException
class FabricException(CommandException):
    pass

# no un-catchable errors from Fabric
env.abort_exception = FabricException

NetworkError = fab_exceptions.NetworkError

#
# api
#

local = fab_api.local
execute = fab_api.execute
parallel = fab_api.parallel
serial = fab_api.serial
hide = fab_api.hide

# https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L158-L241
def settings(*args, **kwargs):

    # these values were set with `fabric.state.output[key] = val`
    # they would be persistant until the program exited
    # - https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L448-L474
    for key, val in kwargs.pop('fabric.state.output', {}).items():
        fabric.state.output[key] = val

    return fab_api.settings(*args, **kwargs)

lcd = fab_api.lcd # local change dir
rcd = fab_api.cd # remote change dir

remote = fab_api.run
remote_sudo = fab_api.sudo
upload = fab_api.put
download = fab_api.get
remote_file_exists = fab_files.exists

# https://github.com/mathiasertl/fabric/blob/master/fabric/utils.py#L30-L63
def abort(msg):
    msg = "\nFatal error: %s\nAborting" % msg
    sys.stderr.write(msg)
    sys.stderr.flush()
    exit(1)

#
# aliases/deprecated api
#

cd = rcd
put = upload
get = download
run = remote
sudo = remote_sudo

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
        runfn = sudo if use_sudo else run
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
