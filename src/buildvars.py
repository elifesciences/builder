from buildercore.bvars import encode_bvars, read_from_current_host
from buildercore.command import remote_sudo, upload
from io import StringIO
from decorators import requires_aws_stack
from buildercore.config import BOOTSTRAP_USER
from buildercore.core import stack_all_ec2_nodes, current_node_id
from buildercore.context_handler import load_context
from buildercore import utils as core_utils, trop, keypair
from buildercore.utils import ensure
from pprint import pprint
import utils
import logging
LOG = logging.getLogger(__name__)

OLD, ABBREV, FULL = 'old', 'abbrev', 'full'

@requires_aws_stack
def switch_revision(stackname, revision=None, concurrency=None):
    if revision is None:
        revision = utils.uin('revision', None)

    def _switch_revision_single_ec2_node():
        buildvars = _retrieve_build_vars()

        if 'revision' in buildvars and revision == buildvars['revision']:
            print('FYI, the instance is already on that revision!')
            return

        new_data = buildvars
        new_data['revision'] = revision
        _update_remote_bvars(stackname, new_data)

    stack_all_ec2_nodes(stackname, _switch_revision_single_ec2_node, username=BOOTSTRAP_USER, concurrency=concurrency)

@requires_aws_stack
def read(stackname):
    "returns the unencoded build variables found on given instance"
    return stack_all_ec2_nodes(stackname, lambda: pprint(read_from_current_host()), username=BOOTSTRAP_USER)

@requires_aws_stack
def valid(stackname):
    return stack_all_ec2_nodes(stackname, lambda: pprint(_retrieve_build_vars()), username=BOOTSTRAP_USER)

def _retrieve_build_vars():
    """wrapper around `read_from_current_host` with integrity checks. returns buildvars for the current instance.
    raises AssertionError on bad data."""
    try:
        buildvars = read_from_current_host()
        LOG.debug('build vars: %s', buildvars)

        # buildvars exist
        ensure(isinstance(buildvars, dict), 'build vars not found (%s). use `./bldr buildvars.fix` to attempt to fix this.' % buildvars)

        # nothing important is missing
        missing_keys = core_utils.missingkeys(buildvars, ['stackname', 'instance_id', 'branch', 'revision'])
        ensure(
            len(missing_keys) == 0,
            'build vars are not valid: missing keys %s. use `./bldr buildvars.fix` to attempt to fix this.' % missing_keys
        )

        return buildvars

    except (ValueError, AssertionError) as ex:
        LOG.exception(ex)
        raise

@requires_aws_stack
def fix(stackname):
    def _fix_single_ec2_node(stackname):
        LOG.info("checking build vars on node %s", current_node_id())
        try:
            buildvars = _retrieve_build_vars()
            LOG.info("valid bvars found, no fix necessary: %s", buildvars)
        except AssertionError:
            LOG.info("invalid build vars found, regenerating from context")
            context = load_context(stackname)
            # some contexts are missing stackname
            context['stackname'] = stackname
            node_id = current_node_id()
            new_vars = trop.build_vars(context, node_id)
            _update_remote_bvars(stackname, new_vars)

    stack_all_ec2_nodes(stackname, (_fix_single_ec2_node, {'stackname': stackname}), username=BOOTSTRAP_USER)

# TODO: deletion candidate. can only ever do a shallow update
@requires_aws_stack
def force(stackname, field, value):
    "replace a specific key with a new value in the buildvars for all ec2 instances in stack"
    def _force_single_ec2_node():
        buildvars = read_from_current_host()

        new_vars = buildvars.copy()
        new_vars[field] = value
        _update_remote_bvars(stackname, new_vars)
        LOG.info("updated bvars %s", new_vars)

    stack_all_ec2_nodes(stackname, _force_single_ec2_node, username=BOOTSTRAP_USER)

def _update_remote_bvars(stackname, buildvars):
    LOG.info('updating %r with new vars %r', stackname, buildvars)
    # not all projects have a 'revision'
    #ensure(core_utils.hasallkeys(buildvars, ['revision']), "buildvars missing key 'revision'")

    encoded = encode_bvars(buildvars)
    fid = core_utils.ymd(fmt='%Y%m%d%H%M%S')
    # make a backup
    remote_sudo('if [ -f /etc/build-vars.json.b64 ]; then cp /etc/build-vars.json.b64 /tmp/build-vars.json.b64.%s; fi;' % fid)
    upload(StringIO(encoded), "/etc/build-vars.json.b64", use_sudo=True)
    LOG.info("%r updated", stackname)

#
#
#

@requires_aws_stack
def refresh(stackname, context):
    "(safely) replaces the buildvars file on the ec2 instance(s)"

    def _refresh_buildvars():
        old_buildvars = _retrieve_build_vars()

        node = old_buildvars.get('node')
        if not node or not str(node).isdigit():
            # (very) old buildvars. try parsing 'nodename'
            nodename = old_buildvars.get('nodename')
            if nodename: # ll: "elife-dashboard--prod--1"
                node = nodename.split('--')[-1]
                if not node.isdigit():
                    LOG.warning("nodename ends in a non-digit node: %s", nodename)
                    node = None

            if not node:
                # no 'node' and no (valid) 'nodename' present
                # assume this stack was created before nodes were a thing
                # and that there is only 1 in the 'cluster'.
                node = 1

        new_buildvars = trop.build_vars(context, int(node))
        new_buildvars['revision'] = old_buildvars.get('revision') # TODO: is this still necessary?
        _update_remote_bvars(stackname, new_buildvars)

    # lsh@2019-06: cfn.update_infrastructure fails to run highstate on new ec2 instance if keypair not present,
    # it prompts for a password for the deploy user. prompts when executing in parallel cause operation to fail
    keypair.download_from_s3(stackname, die_if_exists=False)

    stack_all_ec2_nodes(stackname, _refresh_buildvars, username=BOOTSTRAP_USER)
