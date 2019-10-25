# Fabric 1.14 documentation: https://docs.fabfile.org/en/1.14/

# from buildercore import utils # don't do this, utils depends on command.py
import sys
import fabric.api as fab_api
import fabric.contrib as fab_contrib
#from fabric.api import env

local = fab_api.local
execute = fab_api.execute
parallel = fab_api.parallel
serial = fab_api.serial
hide = fab_api.hide

# https://github.com/mathiasertl/fabric/blob/master/fabric/context_managers.py#L158-L241
settings = fab_api.settings
cd = fab_api.cd
lcd = fab_api.lcd

#
# replacements
#

def remote(*args, **kwargs):
    return fab_api.run(*args, **kwargs)

def remote_sudo(*args, **kwargs):
    return fab_api.sudo(*args, **kwargs)

def upload(*args, **kwargs):
    return fab_api.put(*args, **kwargs)

def download(*args, **kwargs):
    return fab_api.get(*args, **kwargs)

def remote_file_exists(*args, **kwargs):
    return fab_contrib.files.exists(*args, **kwargs)

# https://github.com/mathiasertl/fabric/blob/master/fabric/utils.py#L30-L63
def abort(msg):
    msg = "\nFatal error: %s\nAborting" % msg
    sys.stderr.write(msg)
    sys.stderr.flush()
    exit(1)

#
# aliases and deprecated
#

put = upload # see also: buildercore.utils.fab_put and fab_put_data
get = download # see also: buildercore.utils.fab_get
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
