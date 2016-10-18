from buildercore.bvars import encode_bvars, read_from_current_host
from fabric.api import sudo, put, hide
from StringIO import StringIO
from decorators import requires_aws_stack, debugtask
from buildercore.core import stack_all_ec2_nodes
from buildercore import utils as core_utils
from pprint import pprint
import utils
import logging
LOG = logging.getLogger(__name__)

OLD, ABBREV, FULL = 'old', 'abbrev', 'full'

@debugtask
@requires_aws_stack
def switch_revision(stackname, revision=None):
    if revision is None:
        revision = utils.uin('revision', None)

    def _switch_revision_single_ec2_node():
        buildvars = _retrieve_build_vars()

        if 'revision' in buildvars and revision == buildvars['revision']:
            print 'FYI, the instance is already on that revision!'
            return

        new_data = buildvars
        new_data['revision'] = revision
        _update_remote_bvars(stackname, new_data)

    stack_all_ec2_nodes(stackname, _switch_revision_single_ec2_node)

@debugtask
@requires_aws_stack
def read(stackname):
    "returns the unencoded build variables found on given instance"
    return stack_all_ec2_nodes(stackname, lambda: pprint(read_from_current_host()))

@debugtask
@requires_aws_stack
def valid(stackname):
    return stack_all_ec2_nodes(stackname, lambda: pprint(_validate()))

def _validate():
    "returns a pair of (type, build data) for the given instance. type is either 'old', 'abbrev' or 'full'"
    try:
        buildvars = read_from_current_host()
        bvarst = _bvarstype(buildvars)
        assert bvarst in [None, OLD, ABBREV, FULL], \
            "the build vars found were structured unfamiliarly"
        LOG.debug('bvars (%s): %s', bvarst, buildvars)
        return bvarst, buildvars

    except (ValueError, AssertionError) as ex:
        LOG.exception(ex)
        raise

@debugtask
@requires_aws_stack
def fix(stackname):
    def _fix_single_ec2_node():
        bvarst, _ = _validate()
        if bvarst is None:
            LOG.info("no build vars found, adding defaults")
            new_vars = {'branch': 'master', 'revision': None}
            _update_remote_bvars(stackname, new_vars)
        else:
            LOG.info("valid bvars found (%s), no fix necessary", bvarst)

    stack_all_ec2_nodes(stackname, _fix_single_ec2_node)

@debugtask
@requires_aws_stack
def force(stackname, field, value):
    def _force_single_ec2_node():
        _, build_vars = _validate()
        if build_vars is None:
            raise RuntimeError("no build vars, found")

        new_vars = build_vars.copy()
        new_vars[field] = value
        _update_remote_bvars(stackname, new_vars)
        LOG.info("updated bvars %s", new_vars)

    stack_all_ec2_nodes(stackname, _force_single_ec2_node)

def _retrieve_build_vars():
    print 'looking for build vars ...'
    with hide('everything'):
        bvarst, buildvars = _validate()
    assert bvarst in [ABBREV, FULL], \
        "the build-vars.json file for %r is not valid. use `./bldr buildvars.fix` to attempt to fix this."
    print 'found build vars'
    print
    return buildvars

def _update_remote_bvars(stackname, buildvars):
    LOG.info('updating %r with new vars %r', stackname, buildvars)
    assert core_utils.hasallkeys(buildvars, ['branch'])  # , 'revision']) # we don't use 'revision'

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
    return FULL
