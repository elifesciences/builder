from distutils.util import strtobool as _strtobool  # pylint: disable=import-error,no-name-in-module
import json
from pprint import pformat
from fabric.api import task, local, run, sudo, put, get, abort, settings
import fabric.state
from fabric.contrib import files
import aws, utils, buildvars
from decorators import requires_project, requires_aws_stack, requires_steady_stack, echo_output, setdefault, debugtask, timeit
from buildercore import core, cfngen, utils as core_utils, bootstrap, project, checks, lifecycle as core_lifecycle, context_handler
from buildercore.concurrency import concurrency_for
from buildercore.core import stack_conn, stack_pem, stack_all_ec2_nodes
from buildercore.decorators import PredicateException
from buildercore.config import DEPLOY_USER, BOOTSTRAP_USER, FabricException
from buildercore.utils import lmap

import logging
LOG = logging.getLogger(__name__)

def strtobool(x):
    return x if isinstance(x, bool) else bool(_strtobool(x))

# these aliases are deprecated
@task(alias='aws_delete_stack')
@requires_steady_stack
def destroy(stackname):
    "tell aws to delete a stack."
    print('this is a BIG DEAL. you cannot recover from this.')
    print('type the name of the stack to continue or anything else to quit')
    uin = utils.get_input('> ')
    if not uin or not uin.strip().lower() == stackname.lower():
        import difflib
        print('you needed to type "%s" to continue.' % stackname)
        print('got:')
        print('\n'.join(difflib.ndiff([stackname], [uin])))
        exit(1)
    return bootstrap.delete_stack(stackname)

@task
def ensure_destroyed(stackname):
    try:
        return bootstrap.delete_stack(stackname)
    except PredicateException as e:
        if "I couldn't find a cloudformation stack" in str(e):
            print("Not even the CloudFormation template exists anymore, exiting idempotently")
            return
        raise

# these aliases are deprecated
@task(alias='aws_update_stack')
@requires_aws_stack
@timeit
def update(stackname, autostart="0", concurrency='serial'):
    """Updates the environment within the stack's ec2 instance.
    does *not* call Cloudformation's `update` command on the stack"""
    instances = _check_want_to_be_running(stackname, strtobool(autostart))
    if not instances:
        return
    return bootstrap.update_stack(stackname, service_list=['ec2'], concurrency=concurrency)

@task
@timeit
def update_template(stackname):
    """Limited update of the Cloudformation template.

    Resources can be added, but most of the existing ones are immutable.

    Some resources are updatable in place.

    Moreover, we never add anything related to EC2 instances as they are
    not supported anyway (they will come up as part of the template
    but without any software being on it)

    Moreover, EC2 instances must be running while this is executed or their
    resources like PublicIP will be inaccessible"""

    (pname, _) = core.parse_stackname(stackname)
    more_context = {}
    current_template = bootstrap.current_template(stackname)
    context, delta, current_context = cfngen.regenerate_stack(stackname, current_template, **more_context)

    if _are_there_existing_servers(current_context):
        core_lifecycle.start(stackname)
    LOG.info("Create: %s", pformat(delta.plus))
    LOG.info("Update: %s", pformat(delta.edit))
    LOG.info("Delete: %s", pformat(delta.minus))
    LOG.info("New Terraform generated file: %s", pformat(json.loads(delta.terraform)))
    utils.confirm('Confirming changes to the stack template? This will rewrite the context and the CloudFormation template. Notice the delta *only shows changes to the template*, not to the context.')

    context_handler.write_context(stackname, context)

    if delta.non_empty:
        new_template = cfngen.merge_delta(stackname, delta)
        bootstrap.update_template(stackname, new_template)
    else:
        # attempting to apply an empty change set would result in an error
        LOG.info("Nothing to update on CloudFormation")

    # TODO: all of the following could possibly be moved
    # inside bootstrap.update_stack, if it was smart enough
    # EC2
    if _are_there_existing_servers(context):
        # the /etc/buildvars.json file may need to be updated
        buildvars.refresh(stackname, context)
        update(stackname)

    # SQS
    if context.get('sqs', {}):
        bootstrap.update_stack(stackname, service_list=['sqs'])

    # S3
    if context.get('s3', {}):
        bootstrap.update_stack(stackname, service_list=['s3'])

    # Fastly via Terraform
    if context.get('fastly', {}):
        bootstrap.update_stack(stackname, service_list=['fastly'])


# TODO: this task should probably live in `master.py`
@debugtask
def update_master():
    master_stackname = core.find_master(aws.find_region())
    bootstrap.update_stack(master_stackname, service_list=[
        'ec2' # master-server should be a self-contained EC2 instance
    ])
    bootstrap.remove_all_orphaned_keys(master_stackname)

@requires_project
def generate_stack_from_input(pname, instance_id=None, alt_config=None):
    """creates a new CloudFormation file for the given project."""
    instance_id = instance_id or utils.uin("instance id", core_utils.ymd())
    stackname = core.mk_stackname(pname, instance_id)
    more_context = {'stackname': stackname}

    pdata = project.project_data(pname)
    if alt_config:
        core_utils.ensure('aws-alt' in pdata, "alternative configuration name given, but project has no alternate configurations")

    # prompt user for alternate configurations
    if 'aws-alt' in pdata:
        def helpfn(altkey):
            try:
                return pdata['aws-alt'][altkey]['description']
            except KeyError:
                return None
        if instance_id in pdata['aws-alt'].keys():
            LOG.info("instance-id found in known alternative configurations. using configuration %r", instance_id)
            more_context['alt-config'] = instance_id
        else:
            default = 'skip this step'
            alt_config_choices = [default] + list(pdata['aws-alt'].keys())
            if not alt_config:
                alt_config = utils._pick('alternative config', alt_config_choices, helpfn=helpfn)
            if alt_config != default:
                more_context['alt-config'] = alt_config
    cfngen.generate_stack(pname, **more_context)
    return stackname

# these aliases are deprecated
@task(alias='aws_launch_instance')
@requires_project
def launch(pname, instance_id=None, alt_config=None, **kwargs):
    try:
        stackname = generate_stack_from_input(pname, instance_id, alt_config)
        pdata = core.project_data_for_stackname(stackname)

        print('attempting to create stack:')
        print('  stackname:\t' + stackname)
        print('  region:\t' + pdata['aws']['region'])

        for key, val in kwargs.items():
            print('  %s:\t%s' % (key, pformat(val)))

        print()

        if core.is_master_server_stack(stackname):
            if not checks.can_access_builder_private(pname):
                print("failed to access your organisation's 'builder-private' repository:")
                print('  ' + pdata['private-repo'])
                print("you'll need access to this repository to add a deploy key later")
                print()
                return

        if not core.stack_is_active(stackname):
            LOG.info('stack %s does not exist, creating', stackname)
            bootstrap.create_stack(stackname)

        LOG.info('updating stack %s', stackname)
        bootstrap.update_stack(stackname, **kwargs)
        setdefault('.active-stack', stackname)

    except core.NoMasterException as e:
        LOG.warn(e)
        print("\n%s\nNo master server found, you'll need to `launch` a master-server first." % e)

@debugtask
@requires_aws_stack
def highstate(stackname):
    "a fast update with many caveats. prefer `update` instead"
    with stack_conn(stackname, username=BOOTSTRAP_USER):
        bootstrap.run_script('highstate.sh')

@debugtask
@requires_aws_stack
def pillar(stackname):
    "returns the pillar data a minion is using"
    with stack_conn(stackname, username=BOOTSTRAP_USER):
        sudo('salt-call pillar.items')

@debugtask
@echo_output
def aws_stack_list():
    "returns a list of realized stacks. does not include deleted stacks"
    region = aws.find_region()
    return core.active_stack_names(region)

def _pick_node(instance_list, node):
    instance_list = sorted(instance_list, key=lambda n: n.tags['Name'])
    info = [n for n in instance_list]

    def helpfn(pick):
        node = pick - 1
        return "%s (%s, %s)" % (info[node].tags['Name'], info[node].id, info[node].ip_address)

    num_instances = len(instance_list)
    if num_instances > 1:
        if not node:
            node = utils._pick('node', list(range(1, num_instances + 1)), helpfn=helpfn)
        node = int(node) - 1
        instance = instance_list[int(node)]
    else:
        assert node == 1 or node is None, "You can't specify a node different from 1 for a single-instance stack"
        instance = instance_list[0]
    core_utils.ensure(instance.ip_address is not None, "Selected instance does not have a public ip address, are you sure it's running?")
    return instance


def _are_there_existing_servers(context):
    if not 'ec2' in context:
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
        LOG.warn(e)

    instance_list = core.find_ec2_instances(stackname, allow_empty=True)
    num_instances = len(instance_list)
    if num_instances >= 1:
        return instance_list

    if not autostart:
        should_start = utils._pick('should_start', [True, False], message='Stack not running. Should it be started?')
        if not should_start:
            return False

    core_lifecycle.start(stackname)
    # to get the ip addresses that are assigned to the now-running instances
    # and that weren't there before
    return core.find_ec2_instances(stackname)

@task
@requires_aws_stack
def ssh(stackname, node=None, username=DEPLOY_USER):
    instances = _check_want_to_be_running(stackname)
    if not instances:
        return
    public_ip = _pick_node(instances, node).ip_address
    _interactive_ssh("ssh %s@%s" % (username, public_ip))

@task
@requires_aws_stack
def owner_ssh(stackname, node=None):
    "maintenance ssh. uses the pem key and the bootstrap user to login."
    instances = _check_want_to_be_running(stackname)
    if not instances:
        return
    public_ip = _pick_node(instances, node).ip_address
    # -i identify file
    _interactive_ssh("ssh %s@%s -i %s" % (BOOTSTRAP_USER, public_ip, stack_pem(stackname)))

def _interactive_ssh(command):
    try:
        local(command)
    except FabricException as e:
        LOG.warn(e)


@task
@requires_aws_stack
def download_file(stackname, path, destination='.', node=None, allow_missing="False", use_bootstrap_user="False"):
    """
    Downloads `path` from `stackname` putting it into the `destination` folder, or the `destination` file if it exists and it is a file.

    If `allow_missing` is "True", a non-existant `path` will be skipped without errors.

    If `use_bootstrap_user` is "True", the owner_ssh user will be used for connecting instead of the standard deploy user.

    Boolean arguments are expressed as strings as this is the idiomatic way of passing them from the command line.
    """
    allow_missing, use_bootstrap_user = lmap(strtobool, [allow_missing, use_bootstrap_user])
    with stack_conn(stackname, username=BOOTSTRAP_USER if use_bootstrap_user else DEPLOY_USER, node=node):
        if allow_missing and not files.exists(path):
            return # skip download
        get(path, destination, use_sudo=True)


@task
@requires_aws_stack
def upload_file(stackname, local_path, remote_path, overwrite=False):
    with stack_conn(stackname):
        print('stack:', stackname)
        print('local:', local_path)
        print('remote:', remote_path)
        print('overwrite:', overwrite)
        utils.get_input('continue?')
        if files.exists(remote_path) and not overwrite:
            print('remote file exists, not overwriting')
            exit(1)
        put(local_path, remote_path)

#
# these might need a better home
#

@task
@requires_aws_stack
# pylint: disable-msg=too-many-arguments
def cmd(stackname, command=None, username=DEPLOY_USER, clean_output=False, concurrency=None, node=None):
    if command is None:
        abort("Please specify a command e.g. ./bldr cmd:%s,ls" % stackname)
    LOG.info("Connecting to: %s", stackname)

    instances = _check_want_to_be_running(stackname)
    if not instances:
        return

    # take out the load of crap that Fabric prints mangling the useful output
    # of a remote command
    custom_settings = {}
    if clean_output:
        fabric.state.output['status'] = False
        fabric.state.output['running'] = False
        custom_settings['output_prefix'] = False

    try:
        with settings(**custom_settings):
            return stack_all_ec2_nodes(
                stackname,
                (run, {'command': command}),
                username=username,
                abort_on_prompts=True,
                concurrency=concurrency_for(stackname, concurrency),
                node=int(node) if node else None
            )
    except FabricException as e:
        LOG.error(e)
        exit(2)
