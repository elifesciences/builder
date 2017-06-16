from distutils.util import strtobool  # pylint: disable=import-error,no-name-in-module
from pprint import pformat
from fabric.api import task, local, run, sudo, put, get, abort, settings
import fabric.state
from fabric.contrib import files
import aws, utils
from decorators import requires_project, requires_aws_stack, requires_steady_stack, echo_output, setdefault, debugtask, timeit
from buildercore import core, cfngen, utils as core_utils, bootstrap, project, checks, lifecycle as core_lifecycle, context_handler
from buildercore.concurrency import concurrency_for
from buildercore.core import stack_conn, stack_pem, stack_all_ec2_nodes
from buildercore.decorators import PredicateException
from buildercore.config import DEPLOY_USER, BOOTSTRAP_USER, FabricException

import logging
LOG = logging.getLogger(__name__)

# these aliases are deprecated
@task(alias='aws_delete_stack')
@requires_steady_stack
def destroy(stackname):
    "tell aws to delete a stack."
    print 'this is a BIG DEAL. you cannot recover from this.'
    print 'type the name of the stack to continue or anything else to quit'
    uin = raw_input('> ')
    if not uin or not uin.strip().lower() == stackname.lower():
        import difflib
        print 'you needed to type "%s" to continue.' % stackname
        print 'got:'
        print '\n'.join(difflib.ndiff([stackname], [uin]))
        exit(1)
    return bootstrap.delete_stack(stackname)
@task
def ensure_destroyed(stackname):
    try:
        return bootstrap.delete_stack(stackname)
    except PredicateException as e:
        if "I couldn't find a cloudformation stack" in str(e):
            print "Not even the CloudFormation template exists anymore, exiting idempotently"
            return
        raise

# these aliases are deprecated
@task(alias='aws_update_stack')
@requires_aws_stack
@timeit
def update(stackname, autostart="0"):
    """Updates the environment within the stack's ec2 instance.
    does *not* call Cloudformation's `update` command on the stack"""
    instances = _check_want_to_be_running(stackname, bool(strtobool(autostart)))
    if not instances:
        return
    return bootstrap.update_stack(stackname, service_list=[], concurrency='serial')

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
    more_context = cfngen.choose_config(stackname)

    context, delta = cfngen.regenerate_stack(pname, **more_context)

    if context['ec2']:
        core_lifecycle.start(stackname)
    LOG.info("%s", pformat(delta))
    utils.confirm('Confirming changes to the stack template? This will rewrite the context and the CloudFormation template')

    context_handler.write_context(stackname, context)

    if delta['Resources'] or delta['Outputs']:
        new_template = cfngen.merge_delta(stackname, delta)
        bootstrap.update_template(stackname, new_template)
    else:
        # attempting to apply an empty change set would result in an error
        LOG.info("Nothing to update on CloudFormation")

    update(stackname)


@task
def update_master():
    return bootstrap.update_stack(core.find_master(aws.find_region()))

@requires_project
def generate_stack_from_input(pname, instance_id=None):
    """creates a new CloudFormation file for the given project."""
    if not instance_id:
        default_instance_id = core_utils.ymd()
        instance_id = utils.uin("instance id", default_instance_id)
    stackname = core.mk_stackname(pname, instance_id)
    more_context = {'stackname': stackname}

    # prompt user for alternate configurations
    pdata = project.project_data(pname)
    if 'aws-alt' in pdata:
        def helpfn(altkey):
            try:
                return pdata['aws-alt'][altkey]['description']
            except KeyError:
                return None
        default = 'skip this step'
        alt_config = [default] + pdata['aws-alt'].keys()
        alt_config = utils._pick('alternative config', alt_config, helpfn=helpfn)
        if alt_config != default:
            more_context['alt-config'] = alt_config
    cfngen.generate_stack(pname, **more_context)
    return stackname

# these aliases are deprecated
@task(alias='aws_launch_instance')
@requires_project
def launch(pname, instance_id=None):
    try:
        stackname = generate_stack_from_input(pname, instance_id)
        pdata = core.project_data_for_stackname(stackname)

        print 'attempting to create stack:'
        print '  stackname: ' + stackname
        print '  region:    ' + pdata['aws']['region']
        print

        if core.is_master_server_stack(stackname):
            if not checks.can_access_builder_private(pname):
                print "failed to access your organisation's 'builder-private' repository:"
                print '  ' + pdata['private-repo']
                print "you'll need access to this repository to add a deploy key later"
                print
                return

        bootstrap.create_update(stackname)
        setdefault('.active-stack', stackname)
    except core.NoMasterException as e:
        LOG.warn(e.message)
        print "\n%s\ntry `./bldr master.create`'" % e.message

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
    num_instances = len(instance_list)
    if num_instances > 1:
        if not node:
            node = utils._pick('node', range(1, num_instances + 1))
        node = int(node) - 1
        instance = instance_list[int(node)]
    else:
        assert node == 1 or node is None, "You can't specify a node different from 1 for a single-instance stack"
        instance = instance_list[0]
    core_utils.ensure(instance.ip_address is not None, "Selected instance does not have a public ip address, are you sure it's running?")
    return instance

def _check_want_to_be_running(stackname, autostart=False):
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
def download_file(stackname, path, destination=None, allow_missing="False", use_bootstrap_user="False"):
    """
    Downloads `path` from `stackname` putting it into the `destination` folder, or the `destination` file if it exists and it is a file.

    If `allow_missing` is "True", a not existing `path` will be skipped without errors.

    If `use_bootstrap_user` is "True", the owner_ssh user will be used for connecting instead of the standard deploy user.

    Boolean arguments are expressed as strings as this is the idiomatic way of passing them from the command line.
    """
    if not destination:
        destination = '.'
    utils.mkdirp(destination)
    with stack_conn(stackname, username=_user(use_bootstrap_user)):
        if _should_be_skipped(path, allow_missing):
            return
        get(path, destination, use_sudo=True)


@task
@requires_aws_stack
def upload_file(stackname, local_path, remote_path, overwrite=False):
    with stack_conn(stackname):
        print 'stack:', stackname
        print 'local:', local_path
        print 'remote:', remote_path
        print 'overwrite:', overwrite
        raw_input('continue?')
        if files.exists(remote_path) and not overwrite:
            print 'remote file exists, not overwriting'
            exit(1)
        put(local_path, remote_path)

def _should_be_skipped(path, allow_missing):
    return not files.exists(path) and strtobool(allow_missing)

def _user(use_bootstrap_user):
    if bool(strtobool(use_bootstrap_user)):
        return BOOTSTRAP_USER
    else:
        return DEPLOY_USER

#
# these might need a better home
#

@task
@requires_aws_stack
def cmd(stackname, command=None, username=DEPLOY_USER, clean_output=False, concurrency=None):
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
                concurrency=concurrency_for(stackname, concurrency))
    except FabricException as e:
        LOG.error(e.message)
        exit(2)

@task
def project_list():
    for org, plist in project.org_project_map().items():
        print org
        for project_name in plist:
            print '  ', project_name
        print

@task
@requires_project
@echo_output
def project_config(pname):
    return core_utils.remove_ordereddict(project.project_data(pname))
