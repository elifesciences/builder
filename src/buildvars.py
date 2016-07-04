from os.path import join
from buildercore import core
from fabric.api import env, sudo, run, local, task, get, put, hide
from StringIO import StringIO
from decorators import echo_output, requires_aws_stack, debugtask
from buildercore.core import stack_conn
from buildercore import utils as core_utils
import base64, json
import utils
import re
import logging
LOG = logging.getLogger(__name__)

OLD, ABBREV, FULL = 'old', 'abbrev', 'full'

class FabricException(Exception):
    pass

env.abort_exception = FabricException

@task
@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None):
    switch_revision(stackname, revision)
    _run_salt(stackname)

@debugtask
@requires_aws_stack
def switch_revision(stackname, revision=None):
    bvars = _retrieve_build_vars(stackname)
    if revision is None:
        revision = utils.uin('revision', None)

    _ensure_revision_is_valid(revision)

    if 'revision' in bvars and revision == bvars['revision']:
        print 'FYI, the instance is already on that revision!'
        return

    new_data = bvars
    new_data['revision'] = revision
    _update_remote_bvars(stackname, new_data)    

@debugtask
@requires_aws_stack
@echo_output
def read(stackname):
    "returns the unencoded build variables found on given instance"
    with stack_conn(stackname):
        # due to a typo we now have two types of file naming in existence
        # prefer hyphenated over underscores
        for fname in ['build-vars.json.b64', 'build_vars.json.b64']:
            try:
                fd = StringIO()
                get(join('/etc/', fname), fd)
                return _decode_bvars(fd.getvalue())
            except FabricException, ex:
                # file not found
                continue

@debugtask
@requires_aws_stack
@echo_output
def valid(stackname):
    "returns a pair of (type, build data) for the given instance. type is either 'old', 'abbrev' or 'full'"
    try:
        bvars = read(stackname)
        bvarst = _bvarstype(bvars)
        assert bvarst in [None, OLD, ABBREV, FULL], \
          "the build vars found were structured unfamiliarly"
        LOG.debug('bvars (%s): %s', bvarst, bvars)
        return bvarst, bvars

    except (ValueError, AssertionError), ex:
        LOG.exception(ex)
        raise

def _retrieve_build_vars(stackname):
    pdata = core.project_data_for_stackname(stackname)
    print 'looking for build vars ...'
    with hide('everything'):
        bvarst, bvars = valid(stackname)
    assert bvarst in [ABBREV, FULL], \
      "the build-vars.json file for %r is not valid. use `./bldr buildvars.fix` to attempt to fix this."
    print 'found build vars'
    print
    return bvars

def _ensure_revision_is_valid(revision):
    if revision and not re.match('^[0-9a-f]+$', revision):
        raise ValueError("'%s' is not a valid revision" % revision)
    
def _update_remote_bvars(stackname, bvars):
    LOG.info('updating %r with new vars %r',stackname, bvars)
    assert core_utils.hasallkeys(bvars, ['branch']) #, 'revision']) # we don't use 'revision'
    with stack_conn(stackname):
        encoded = _encode_bvars(bvars)
        fid = core_utils.ymd(fmt='%Y%m%d%H%M%S')
        cmds = [
            # make a backup
            'if [ -f /etc/build-vars.json.b64 ]; then cp /etc/build-vars.json.b64 /tmp/build-vars.json.b64.%s; fi;' % fid,
            # purge any mention of build vars
            'rm -f /etc/build*vars.*',
        ]
        map(sudo, cmds)
        put(StringIO(encoded), "/etc/build-vars.json.b64", use_sudo=True)
        LOG.info("%r updated", stackname)            

def _run_salt(stackname):
    with stack_conn(stackname):
        return sudo('salt-call state.highstate --retcode-passthrough')

def _bvarstype(bvars):
    "return"
    if not bvars:
        return None
    bvarkeys = bvars.keys()
    if len(bvarkeys) == 1:
        # we have the old-style {'appname': {'branch': ..., 'revision': ...}}
        return OLD
    if len(bvarkeys) == 2:
        # we have the abbreviated build-vars {'branch': ..., 'revision': ... }
        return ABBREV
    if len(bvarkeys) > 2 and core_utils.hasallkeys(bvars, ['author', 'project', 'branch']):
        # we have the huge dump of vars
        return FULL
    raise ValueError("unknown buildvars: %r" % bvars)

def _decode_bvars(contents):
    return json.loads(base64.b64decode(contents))

def _encode_bvars(contents):
    return base64.b64encode(json.dumps(contents))
