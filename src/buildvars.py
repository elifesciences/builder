from buildercore.bvars import encode_bvars, read_from_current_host
from fabric.api import sudo, put, hide
from StringIO import StringIO
from decorators import requires_aws_stack, debugtask
from buildercore.config import BOOTSTRAP_USER
from buildercore.core import stack_all_ec2_nodes, current_node_id
from buildercore.context_handler import load_context
from buildercore.trop import build_vars
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

    stack_all_ec2_nodes(stackname, _switch_revision_single_ec2_node, username=BOOTSTRAP_USER)

@debugtask
@requires_aws_stack
def read(stackname):
    "returns the unencoded build variables found on given instance"
    return stack_all_ec2_nodes(stackname, lambda: pprint(read_from_current_host()), username=BOOTSTRAP_USER)

@debugtask
@requires_aws_stack
def valid(stackname):
    return stack_all_ec2_nodes(stackname, lambda: pprint(_validate()), username=BOOTSTRAP_USER)

def _validate():
    "returns a pair of (type, build data) for the given instance. type is either 'old', 'abbrev' or 'full'"
    try:
        buildvars = read_from_current_host()
        LOG.debug('build vars: %s', buildvars)
        core_utils.ensure(
            isinstance(buildvars, dict),
            'build vars not found (%s). use `./bldr buildvars.fix` to attempt to fix this.',
            buildvars
        )
        for key in ['stackname', 'instance_id', 'branch', 'revision', 'is_prod_instance']:
            core_utils.ensure(
                key in buildvars,
                'build vars are not valid: missing key %s. use `./bldr buildvars.fix` to attempt to fix this.' % key
            )
        return buildvars

    except (ValueError, AssertionError) as ex:
        LOG.exception(ex)
        raise

@debugtask
@requires_aws_stack
def fix(stackname):
    def _fix_single_ec2_node(stackname):
        LOG.info("checking build vars on node %s", current_node_id())
        try:
            buildvars = _validate()
            LOG.info("valid bvars found, no fix necessary: %s", buildvars)
        except AssertionError:
            LOG.info("invalid build vars found, regenerating from context")
            context = load_context(stackname)
            # some contexts are missing stackname
            context['stackname'] = stackname
            node_id = current_node_id()
            new_vars = build_vars(context, node_id)
            _update_remote_bvars(stackname, new_vars)

    stack_all_ec2_nodes(stackname, (_fix_single_ec2_node, {'stackname': stackname}), username=BOOTSTRAP_USER)

@debugtask
@requires_aws_stack
def force(stackname, field, value):
    def _force_single_ec2_node():
        buildvars = read_from_current_host()

        new_vars = buildvars.copy()
        new_vars[field] = value
        _update_remote_bvars(stackname, new_vars)
        LOG.info("updated bvars %s", new_vars)

    stack_all_ec2_nodes(stackname, _force_single_ec2_node, username=BOOTSTRAP_USER)

def _retrieve_build_vars():
    print 'looking for build vars ...'
    with hide('everything'):
        buildvars = _validate()
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
