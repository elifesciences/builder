import os, json
from pprint import pformat
import backoff
from buildercore.command import local, remote, upload, download, settings, remote_file_exists, CommandException, NetworkError
import utils, buildvars
from utils import TaskExit
from decorators import requires_project, requires_aws_stack, requires_aws_stack_template, setdefault, timeit
from buildercore import core, cfngen, utils as core_utils, bootstrap, project, checks, lifecycle as core_lifecycle, context_handler
# potentially remove to go through buildercore.bootstrap?
from buildercore import cloudformation, terraform
from buildercore.concurrency import concurrency_for
from buildercore.core import stack_conn, stack_pem, stack_all_ec2_nodes, tags2dict
from buildercore.decorators import PredicateException
from buildercore.config import DEPLOY_USER, BOOTSTRAP_USER, USER_PRIVATE_KEY
from buildercore.utils import ensure

import logging
LOG = logging.getLogger(__name__)

# TODO: move to a lower level if possible
# @requires_steady_stack
def destroy(stackname):
    "Delete a stack of resources."
    msg = '''this is a BIG DEAL. you cannot recover from this.
type the name of the stack to continue or anything else to quit:
> '''
    uin = utils.get_input(msg)
    if not uin or not uin.strip().lower() == stackname.lower():
        raise TaskExit('you needed to type "%s" to continue.' % stackname)
    return bootstrap.destroy(stackname)

def ensure_destroyed(stackname):
    try:
        return bootstrap.destroy(stackname)
    except context_handler.MissingContextFile:
        LOG.warning("Context does not exist anymore or was never created, exiting idempotently")
    except PredicateException as e:
        if "I couldn't find a cloudformation stack" in str(e):
            LOG.warning("Not even the CloudFormation template exists anymore, exiting idempotently")
            return
        raise

@requires_aws_stack
@timeit
def update(stackname, autostart="0", concurrency='serial', dry_run=False):
    """Update a stack's ec2 environment.
    Runs the (idempotent) bootstrap script then Salt highstate.
    Does *not* call Cloudformation's `update` command on the stack,
    see `update_infrastructure`."""
    instances = _check_want_to_be_running(stackname, utils.strtobool(autostart))
    if not instances:
        return
    dry_run = utils.strtobool(dry_run)
    return bootstrap.update_stack(stackname, service_list=['ec2'], concurrency=concurrency, dry_run=dry_run)

@timeit
def update_infrastructure(stackname, skip=None, start=['ec2']):
    """Limited update of the Cloudformation template and/or Terraform template.

    Resources can be added, but most of the existing ones are immutable.

    Some resources are updatable in place.

    Moreover, we never add anything related to EC2 instances as they are
    not supported anyway (they will come up as part of the template
    but without any software being on it)

    Moreover, EC2 instances must be running while this is executed or their
    resources like PublicIP will be inaccessible.

    Allows to skip EC2, SQS, S3 updates by passing `skip=ec2\\,sqs\\,s3`

    By default starts EC2 instances but this can be avoid by passing `start=`"""

    skip = skip.split(",") if skip else []
    start = start.split(",") if isinstance(start, str) else start or []

    (pname, _) = core.parse_stackname(stackname)
    more_context = {}
    context, delta, current_context = cfngen.regenerate_stack(stackname, **more_context)

    if _are_there_existing_servers(current_context) and 'ec2' in start:
        core_lifecycle.start(stackname)
    LOG.info("Create: %s", pformat(delta.plus))
    LOG.info("Update: %s", pformat(delta.edit))
    LOG.info("Delete: %s", pformat(delta.minus))
    LOG.info("Terraform delta: %s", delta.terraform)

    # see: `buildercore.config.BUILDER_NON_INTERACTIVE` for skipping confirmation prompts
    if not utils.confirm('Confirming changes to CloudFormation and Terraform templates?', 'confirm'):
        raise TaskExit("failed to confirm")

    context_handler.write_context(stackname, context)

    cloudformation.update_template(stackname, delta.cloudformation)
    terraform.update_template(stackname)

    # TODO: move inside bootstrap.update_stack
    # EC2
    if _are_there_existing_servers(context) and "ec2" not in skip:
        # the /etc/buildvars.json file may need to be updated
        buildvars.refresh(stackname, context)
        update(stackname)

    # SQS
    if context.get('sqs', {}) and "sqs" not in skip:
        bootstrap.update_stack(stackname, service_list=['sqs'])

    # S3
    if context.get('s3', {}) and "s3" not in skip:
        bootstrap.update_stack(stackname, service_list=['s3'])

def check_user_input(pname, instance_id=None, alt_config=None):
    "marshals user input and checks it for correctness"
    instance_id = instance_id or utils.uin("instance id", core_utils.ymd())
    stackname = core.mk_stackname(pname, instance_id)
    pdata = project.project_data(pname)

    # alt-config given, die if it doesn't exist
    if alt_config:
        ensure('aws-alt' in pdata, "alt-config %r given, but project has no alternate configurations" % alt_config)

    # if the requested instance-id matches a known alt-config, we'll use that alt-config. warn user.
    if instance_id in pdata['aws-alt'].keys():
        LOG.warn("instance-id %r found in alt-config list, using that.", instance_id)
        alt_config = instance_id

    # no alt-config given but alt-config options exist, prompt user
    if not alt_config and pdata['aws-alt']:
        default_choice = 'skip'

        def helpfn(altkey):
            if altkey == default_choice:
                return 'uses the default configuration'
            try:
                return pdata['aws-alt'][altkey]['description']
            except KeyError:
                return None

        alt_config_choice_list = [default_choice] + list(pdata['aws-alt'].keys())
        alt_config_choice = utils._pick('alternative config', alt_config_choice_list, helpfn=helpfn)
        if alt_config_choice != default_choice:
            alt_config = alt_config_choice

    # check the alt-config isn't unique and if it *is* unique, that an instance using it doesn't exist yet.
    # note: it is *technically* possible that an instance is using a unique configuration but
    # that its instance-id *is not* the name of the alt-config passed in.
    # For example, if `journal--prod` didn't exist, I could create `journal--foo` using the `prod` config.
    if alt_config and alt_config in pdata['aws-alt'] and pdata['aws-alt'][alt_config]['unique']:
        dealbreaker = core.mk_stackname(pname, alt_config)
        # "project 'journal' config 'prod' is marked as unique!"
        # "checking for any instance named 'journal--prod' ..."
        print("project %r config %r is marked as unique!" % (pname, alt_config))
        print("checking for any instance named %r ..." % (dealbreaker,))
        try:
            checks.ensure_stack_does_not_exist(dealbreaker)
        except checks.StackAlreadyExistsProblem:
            # "stack 'journal--prod' exists, cannot re-use unique configuration 'prod'"
            msg = "stack %r exists, cannot re-use unique configuration %r." % (dealbreaker, alt_config)
            raise TaskExit(msg)

    # check that the instance we want to create doesn't exist
    try:
        print("checking %r doesn't exist." % stackname)
        checks.ensure_stack_does_not_exist(stackname)
    except checks.StackAlreadyExistsProblem as e:
        msg = 'stack %r already exists.' % e.stackname
        raise TaskExit(msg)

    more_context = {'stackname': stackname}
    if alt_config:
        more_context['alt-config'] = alt_config

    return more_context

def generate_stack_from_input(pname, instance_id=None, alt_config=None):
    """creates a new CloudFormation/Terraform file for the given project `pname` with
    the identifier `instance_id` using the (optional) project configuration `alt_config`."""
    more_context = check_user_input(pname, instance_id, alt_config)
    stackname = more_context['stackname']

    # ~TODO: return the templates used here, so that they can be passed down to~
    # ~bootstrap.create_stack() without relying on them implicitly existing~
    # ~on the filesystem~
    # lsh@2021-07: having the files on the filesystem with predictable names seems more
    # robust than carrying it around as a parameter through complex logic.
    _, cloudformation_file, terraform_file = cfngen.generate_stack(pname, **more_context)

    if cloudformation_file:
        print('cloudformation template:')
        with open(cloudformation_file, 'r') as fh:
            print(json.dumps(json.load(fh), indent=4))
        print()

    if terraform_file:
        print('terraform template:')
        with open(terraform_file, 'r') as fh:
            print(json.dumps(json.load(fh), indent=4))
        print()

    if cloudformation_file:
        LOG.info('wrote: %s' % os.path.abspath(cloudformation_file))

    if terraform_file:
        LOG.info('wrote: %s' % os.path.abspath(terraform_file))

    # see: `buildercore.config.BUILDER_NON_INTERACTIVE` for skipping confirmation prompts
    if not utils.confirm('the above resources will be created', 'confirm'):
        raise TaskExit('failed to confirm')

    return stackname

@requires_project
def launch(pname, instance_id=None, alt_config=None):
    stackname = generate_stack_from_input(pname, instance_id, alt_config)
    pdata = core.project_data_for_stackname(stackname)

    LOG.info('attempting to create %s (AWS region %s)', stackname, pdata['aws']['region'])

    if core.is_master_server_stack(stackname):
        checks.ensure_can_access_builder_private(pname)

    bootstrap.create_stack(stackname)

    LOG.info('updating stack %s', stackname)
    bootstrap.update_stack(stackname, service_list=['ec2', 'sqs', 's3'])
    setdefault('.active-stack', stackname)


@requires_aws_stack
def fix_bootstrap(stackname):
    """Uploads the bootstrap script and re-runs the bootstrap process.
    Used when stack creation succeeds but the bootstrap script has failed."""
    LOG.info('bootstrapping stack %s', stackname)
    bootstrap.update_stack(stackname)
    setdefault('.active-stack', stackname)

def _pick_node(instance_list, node):
    instance_list = sorted(instance_list, key=lambda n: tags2dict(n.tags)['Name'])
    info = [n for n in instance_list] #

    def helpfn(pick):
        node = pick - 1
        return "%s (%s, %s)" % (tags2dict(info[node].tags)['Name'], info[node].id, info[node].public_ip_address)

    num_instances = len(instance_list)
    if num_instances > 1:
        if not node:
            node = utils._pick('node', list(range(1, num_instances + 1)), helpfn=helpfn)
        node = int(node) - 1
        instance = instance_list[int(node)]
    else:
        ensure(node == 1 or node is None, "You can't specify a node different from 1 for a single-instance stack")
        instance = instance_list[0]
    ensure(instance.public_ip_address, "Selected instance does not have a public ip address, are you sure it's running?")
    return instance


def _are_there_existing_servers(context):
    if "ec2" not in context:
        # very old stack, canned response
        return True

    if isinstance(context['ec2'], bool):
        # no ec2 instances or an instance whose buildvars haven't been updated.
        # either way, the value here can be used as-is
        return context['ec2']

    num_suppressed = len(context['ec2'].get('suppressed', []))
    cluster_size = context['ec2'].get('cluster-size', 1)
    return context['ec2'] and num_suppressed < cluster_size

def _check_want_to_be_running(stackname, autostart=False):
    try:
        context = context_handler.load_context(stackname)
        if not _are_there_existing_servers(context):
            return False

    except context_handler.MissingContextFile as e:
        LOG.warning(e)

    instance_list = core.find_ec2_instances(stackname, allow_empty=True)
    num_instances = len(instance_list)
    if num_instances >= 1:
        return instance_list

    if not autostart:
        should_start = utils._pick('should_start', [True, False], message='Stack not running. Should it be started?')
        if not should_start:
            return False

    core_lifecycle.start(stackname)
    # another call to get the ip addresses that are assigned to the now-running
    # instances and that weren't there before
    return core.find_ec2_instances(stackname)

def _interactive_ssh(username, public_ip, private_key):
    try:
        command = "ssh -o \"ConnectionAttempts 3\" %s@%s -i %s" % (username, public_ip, private_key)
        return local(command)
    except CommandException as e:
        LOG.warning(e)

@requires_aws_stack
def ssh(stackname, node=None, username=DEPLOY_USER):
    "connect to a instance over SSH as 'elife' with *your* private key."
    instances = _check_want_to_be_running(stackname)
    if not instances:
        return
    public_ip = _pick_node(instances, node).public_ip_address
    _interactive_ssh(username, public_ip, USER_PRIVATE_KEY)

@requires_aws_stack
def owner_ssh(stackname, node=None):
    """maintenance ssh.
    connect to an instance over SSH as 'ubuntu' with
    the instance's private key."""
    instances = _check_want_to_be_running(stackname)
    if not instances:
        return
    public_ip = _pick_node(instances, node).public_ip_address
    _interactive_ssh(BOOTSTRAP_USER, public_ip, stack_pem(stackname))

@requires_aws_stack
def download_file(stackname, path, destination='.', node=None, allow_missing="False", use_bootstrap_user="False"):
    """Downloads `path` to the `destination` folder.
    If `allow_missing`, a non-existant `path` will be skipped without errors.
    If `use_bootstrap_user`, the 'ubuntu' user will be used for ssh connections."""
    allow_missing = utils.strtobool(allow_missing)
    use_bootstrap_user = utils.strtobool(use_bootstrap_user)

    @backoff.on_exception(backoff.expo, NetworkError, max_time=60)
    def _download(path, destination):
        with stack_conn(stackname, username=BOOTSTRAP_USER if use_bootstrap_user else DEPLOY_USER, node=node):
            if allow_missing and not remote_file_exists(path):
                return # skip download
            download(path, destination, use_sudo=True)

    _download(path, destination)

@requires_aws_stack
def upload_file(stackname, local_path, remote_path=None, overwrite=False, node=1):
    remote_path = remote_path or os.path.join("/tmp", os.path.basename(local_path))
    # todo: use utils.strtobool
    overwrite = str(overwrite).lower() == "true"
    node = int(node)
    with stack_conn(stackname, node=node):
        print('stack:', stackname, 'node', node)
        print('local:', local_path)
        print('remote:', remote_path)
        print('overwrite:', overwrite)
        utils.confirm('continue?')
        if remote_file_exists(remote_path) and not overwrite:
            print('remote file exists, not overwriting')
            exit(1)
        upload(local_path, remote_path)

#
# these might need a better home
#

@requires_aws_stack
@requires_aws_stack_template
# pylint: disable-msg=too-many-arguments
def cmd(stackname, command=None, username=DEPLOY_USER, clean_output=False, concurrency=None, node=None):
    if command is None:
        utils.errcho("Please specify a command e.g. ./bldr cmd:%s,ls" % stackname)
        exit(1)
    LOG.info("Connecting to: %s", stackname)

    instances = _check_want_to_be_running(stackname)
    if not instances:
        return

    # removes much of the crap emitted that mangles the useful output of a remote command.
    custom_settings = {}
    if clean_output:
        custom_settings = {
            'display_status': False,
            'display_running': False,
            'display_prefix': False,
        }
    try:
        with settings(**custom_settings):
            return stack_all_ec2_nodes(
                stackname,
                (remote, {'command': command}),
                username=username,
                abort_on_prompts=True,
                concurrency=concurrency_for(stackname, concurrency),
                node=int(node) if node else None
            )
    except CommandException as e:
        LOG.error(e)
        exit(2)
