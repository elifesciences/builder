from buildercore.bvars import encode_bvars, read_from_current_host
from fabric.api import sudo, put, hide
from StringIO import StringIO
from decorators import echo_output, requires_aws_stack, debugtask
from buildercore.core import stack_conn
from buildercore import utils as core_utils
import utils
import logging
LOG = logging.getLogger(__name__)

OLD, ABBREV, FULL = 'old', 'abbrev', 'full'

@debugtask
@requires_aws_stack
def switch_revision(stackname, revision=None):
    buildvars = _retrieve_build_vars(stackname)
    if revision is None:
        revision = utils.uin('revision', None)

    if 'revision' in buildvars and revision == buildvars['revision']:
        print 'FYI, the instance is already on that revision!'
        return

    new_data = buildvars
    new_data['revision'] = revision
    _update_remote_bvars(stackname, new_data)    

@debugtask
@requires_aws_stack
@echo_output
def read(stackname):
    "returns the unencoded build variables found on given instance"
    with stack_conn(stackname):
        return read_from_current_host()

@debugtask
@requires_aws_stack
@echo_output
def valid(stackname):
    "returns a pair of (type, build data) for the given instance. type is either 'old', 'abbrev' or 'full'"
    try:
        buildvars = read(stackname)
        bvarst = _bvarstype(buildvars)
        assert bvarst in [None, OLD, ABBREV, FULL], \
          "the build vars found were structured unfamiliarly"
        LOG.debug('bvars (%s): %s', bvarst, buildvars)
        return bvarst, buildvars

    except (ValueError, AssertionError), ex:
        LOG.exception(ex)
        raise

@debugtask
@requires_aws_stack
@echo_output
def fix(stackname):
    bvarst, _ = valid(stackname)
    if bvarst is None:
        LOG.info("no build vars found, adding defaults")
        new_vars = {'branch': 'master', 'revision': None}
        _update_remote_bvars(stackname, new_vars)
    else:
        LOG.info("valid bvars found (%s), no fix necessary", bvarst)

def _retrieve_build_vars(stackname):
    #pdata = core.project_data_for_stackname(stackname)
    print 'looking for build vars ...'
    with hide('everything'):
        bvarst, buildvars = valid(stackname)
    assert bvarst in [ABBREV, FULL], \
      "the build-vars.json file for %r is not valid. use `./bldr buildvars.fix` to attempt to fix this."
    print 'found build vars'
    print
    return buildvars

def _update_remote_bvars(stackname, buildvars):
    LOG.info('updating %r with new vars %r',stackname, buildvars)
    assert core_utils.hasallkeys(buildvars, ['branch']) #, 'revision']) # we don't use 'revision'
    with stack_conn(stackname):
        encoded = encode_bvars(buildvars)
        fid = core_utils.ymd(fmt='%Y%m%d%H%M%S')
        cmds = [
            # make a backup
            'if [ -f /etc/build-vars.json.b64 ]; then cp /etc/build-vars.json.b64 /tmp/build-vars.json.b64.%s; fi;' % fid,
        ]
        map(sudo, cmds)
        put(StringIO(encoded), "/etc/build-vars.json.b64", use_sudo=True)
        LOG.info("%r updated", stackname)            


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
