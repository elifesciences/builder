from buildercore.bvars import encode_bvars, read_from_current_host
from buildercore.command import remote_sudo, upload
from io import StringIO
from decorators import requires_aws_stack, format_output
from buildercore.config import BOOTSTRAP_USER
from buildercore.core import stack_all_ec2_nodes, current_node_id
from buildercore.context_handler import load_context
from buildercore import utils as core_utils, trop, keypair
from buildercore.utils import ensure
import utils
import logging
from json import JSONDecodeError

LOG = logging.getLogger(__name__)

OLD, ABBREV, FULL = 'old', 'abbrev', 'full'

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

    except (ValueError, AssertionError, JSONDecodeError) as ex:
        LOG.exception(ex)
        raise

def _update_remote_bvars(stackname, buildvars):
    LOG.debug('updating %r with new vars %r', stackname, buildvars)
    encoded = encode_bvars(buildvars)
    fid = core_utils.ymd(fmt='%Y%m%d%H%M%S')
    # make a backup
    remote_sudo('if [ -f /etc/build-vars.json.b64 ]; then cp /etc/build-vars.json.b64 /tmp/build-vars.json.b64.%s; fi;' % fid)
    upload(StringIO(encoded), "/etc/build-vars.json.b64", use_sudo=True)
    LOG.info("%r updated. backup written to /tmp/build-vars.json.b64.%s", stackname, fid)

# ---

@format_output('python')
@requires_aws_stack
def read(stackname):
    "returns the unencoded build variables found on given `stackname`"
    return stack_all_ec2_nodes(stackname, lambda: read_from_current_host(), username=BOOTSTRAP_USER)

@format_output('python')
@requires_aws_stack
def valid(stackname):
    return stack_all_ec2_nodes(stackname, lambda: _retrieve_build_vars(), username=BOOTSTRAP_USER)

@requires_aws_stack
def fix(stackname):
    def _fix_single_ec2_node(stackname):
        LOG.info("checking build vars on node %s", current_node_id())
        try:
            _retrieve_build_vars()
            LOG.info("valid bvars found, no fix necessary.")
            return
        except AssertionError as ae:
            LOG.info("invalid build vars found (AssertionError): %s", ae)
        except JSONDecodeError as jde:
            LOG.info("invalid build vars found (JSONDecodeError): %s", jde)
        except ValueError as ve:
            LOG.info("invalid build vars found (ValueError): %s", ve)

        LOG.info("regenerating buildvars from context")

        context = load_context(stackname)
        # some contexts are missing stackname
        context['stackname'] = stackname
        node_id = current_node_id()
        new_vars = trop.build_vars(context, node_id)
        _update_remote_bvars(stackname, new_vars)

    stack_all_ec2_nodes(stackname, (_fix_single_ec2_node, {'stackname': stackname}), username=BOOTSTRAP_USER)

@requires_aws_stack
def switch_revision(stackname, revision=None, concurrency=None):
    revision = revision or utils.uin('revision', None)
    ensure(revision, "a revision is required", utils.TaskExit)

    fix(stackname)

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
def force(stackname, field, new_value):
    """Force a change to a single buildvar.
    Replaces the value of `field` with `new_value` in all buildvars on all
    ec2 instances in given `stackname`.
    Can only be used to *replace* an *existing* key and not create new ones.
    `field` can be a dotted path for targeting values inside nested maps.
    For example: `force("lax--prod", "elb.stickiness", True)`"""

    new_value = utils.coerce_string_value(new_value)

    def _force_single_ec2_node():
        buildvars = read_from_current_host()
        new_buildvars = core_utils.deepcopy(buildvars)
        new_buildvars = core_utils.updatein(buildvars, field, new_value, create=False)
        _update_remote_bvars(stackname, new_buildvars)
        LOG.debug("updated bvars %s", new_buildvars)

    stack_all_ec2_nodes(stackname, _force_single_ec2_node, username=BOOTSTRAP_USER)

@requires_aws_stack
def refresh(stackname, context=None):
    "(safely) replaces the buildvars file on the ec2 instance(s)"

    context = context or load_context(stackname)

    def _refresh_buildvars():
        old_buildvars = _retrieve_build_vars()

        node = old_buildvars.get('node')
        if not node or not str(node).isdigit():
            # (very) old buildvars. try parsing 'nodename'
            nodename = old_buildvars.get('nodename')
            if nodename: # "elife-dashboard--prod--1"
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

    # lsh@2019-06: cfn.update_infrastructure fails to run highstate on new (unvisited? not the instance author?)
    # ec2 instance if keypair not present, it prompts for a password for the deploy user. prompts when executing
    # in parallel cause operation to fail.
    keypair.download_from_s3(stackname, die_if_exists=False)

    stack_all_ec2_nodes(stackname, _refresh_buildvars, username=BOOTSTRAP_USER)
