"""Logic for provisioning and bootstrapping an automatically
created Cloudformation template.

The "stackname" parameter these functions take is the name of the cfn template
without the extension."""

import os, json, re
from os.path import join
from pprint import pformat
from functools import partial
from StringIO import StringIO
from . import core, utils, config, keypair, bvars
from collections import OrderedDict
from datetime import datetime
from .core import connect_aws_with_stack, stack_pem, stack_all_ec2_nodes, project_data_for_stackname, stack_conn
from .utils import first, call_while, ensure, subdict, yaml_dump
from .lifecycle import delete_dns
from .config import BOOTSTRAP_USER
from fabric.api import sudo, put
import fabric.exceptions as fabric_exceptions
from fabric.contrib import files
from fabric import operations
from boto.exception import BotoServerError
from kids.cache import cache as cached
from buildercore import context_handler, project, utils as core_utils
from functools import reduce # pylint:disable=redefined-builtin

import logging
LOG = logging.getLogger(__name__)

#
# utils
#
def _put_temporary_script(script_filename):
    local_script = join(config.SCRIPTS_PATH, script_filename)
    start = datetime.now()
    timestamp_marker = start.strftime("%Y%m%d%H%M%S")
    remote_script = join('/tmp', os.path.basename(script_filename) + '-' + timestamp_marker)
    put(local_script, remote_script)
    return remote_script

def put_script(script_filename, remote_script):
    """uploads a script for SCRIPTS_PATH in remote_script location, making it executable
    ASSUMES YOU ARE CONNECTED TO A STACK"""
    temporary_script = _put_temporary_script(script_filename)
    sudo("mv %s %s && chmod +x %s" % (temporary_script, remote_script, remote_script))

def run_script(script_filename, *script_params, **environment_variables):
    """uploads a script for SCRIPTS_PATH and executes it in the /tmp dir with given params.
    ASSUMES YOU ARE CONNECTED TO A STACK"""
    start = datetime.now()
    remote_script = _put_temporary_script(script_filename)

    def escape_string_parameter(parameter):
        return "'%s'" % parameter

    env_string = ['%s=%s' % (k, v) for k, v in environment_variables.items()]
    cmd = ["/bin/bash", remote_script] + map(escape_string_parameter, list(script_params))
    retval = sudo(" ".join(env_string + cmd))
    sudo("rm " + remote_script) # remove the script after executing it
    end = datetime.now()
    LOG.info("Executed script %s in %2.4f seconds", script_filename, (end - start).total_seconds())
    return retval

def prep_ec2_instance():
    """called after stack creation and before AMI creation"""
    return run_script("prep-stack.sh")


#
# provision stack
#

def _noop():
    pass

def create_stack(stackname):
    pdata = project_data_for_stackname(stackname)
    parameters = []
    on_start = _noop
    on_error = _noop
    if pdata['aws']['ec2']:
        parameters.append(('KeyName', stackname))
        on_start = lambda: keypair.create_keypair(stackname)
        on_error = lambda: keypair.delete_keypair(stackname)

    return _create_generic_stack(stackname, parameters, on_start, on_error)

def _create_generic_stack(stackname, parameters=None, on_start=_noop, on_error=_noop):
    "simply creates the stack of resources on AWS, talking to CloudFormation."
    if not parameters:
        parameters = []

    LOG.info('creating stack %r', stackname)
    stack_body = core.stack_json(stackname)
    try:
        on_start()
        conn = connect_aws_with_stack(stackname, 'cfn')
        conn.create_stack(stackname, stack_body, parameters=parameters)
        _wait_until_in_progress(stackname)
        context = context_handler.load_context(stackname)
        # setup various resources after creation, where necessary
        setup_ec2(stackname, context['ec2'])

        return True
    except StackTakingALongTimeToComplete as err:
        LOG.info("Stack taking a long time to complete: %s", err.message)
        raise
    except BotoServerError as err:
        if err.message.endswith(' already exists'):
            LOG.debug(err.message)
            return False
        LOG.exception("unhandled Boto exception attempting to create stack", extra={'stackname': stackname, 'parameters': parameters})
        on_error()
        raise
    except KeyboardInterrupt:
        LOG.debug("caught keyboard interrupt, cancelling...")
        return False
    except BaseException:
        LOG.exception("unhandled exception attempting to create stack", extra={'stackname': stackname})
        on_error()
        raise

class StackTakingALongTimeToComplete(RuntimeError):
    pass

def _wait_until_in_progress(stackname):
    def is_updating(stackname):
        stack_status = core.describe_stack(stackname).stack_status
        LOG.info("Stack status: %s", stack_status)
        return stack_status in ['CREATE_IN_PROGRESS']
    utils.call_while(
        partial(is_updating, stackname),
        timeout=7200,
        update_msg='Waiting for AWS to finish creating stack ...',
        exception_class=StackTakingALongTimeToComplete
    )
    final_stack = core.describe_stack(stackname)
    events = [(e.resource_status, e.resource_status_reason) for e in final_stack.describe_events()]
    ensure(final_stack.stack_status in ['CREATE_COMPLETE'],
           "Failed to create stack: %s.\nEvents: %s" % (final_stack.stack_status, pformat(events)))

def setup_ec2(stackname, context_ec2):
    if not context_ec2:
        return

    def _setup_ec2_node():
        def is_resourcing():
            try:
                # we have an issue where the stack is created, however the security group
                # hasn't been attached or ssh isn't running yet and we can't get in.
                # this waits until a connection can be made and a file is found before continuing.
                # moreover, call until:
                # - bootstrap user exists and we can access it through SSH
                # - cloud-init has finished running
                #       otherwise we may be missing /etc/apt/source.list, which is generated on boot
                #       https://www.digitalocean.com/community/questions/how-to-make-sure-that-cloud-init-finished-running
                return not files.exists(join('/home', BOOTSTRAP_USER, ".ssh/authorized_keys")) \
                    or not files.exists('/var/lib/cloud/instance/boot-finished')
            except fabric_exceptions.NetworkError:
                LOG.debug("failed to connect to server ...")
                return True
        utils.call_while(is_resourcing, interval=3, update_msg='Waiting for /home/ubuntu to be detected ...')

    stack_all_ec2_nodes(stackname, _setup_ec2_node, username=BOOTSTRAP_USER)


def update_sqs_stack(stackname, **kwargs):
    pdata = project_data_for_stackname(stackname)
    if not pdata['aws']['sqs']:
        return
    context = context_handler.load_context(stackname)
    setup_sqs(stackname, context.get('sqs', {}), pdata['aws']['region'])

def setup_sqs(stackname, context_sqs, region):
    """
    Connects SQS queues created by Cloud Formation to SNS topics where
    necessary, adding both the subscription and the IAM policy to let the SNS
    topic write to the queue
    """
    assert isinstance(context_sqs, dict), ("Not a dictionary of queues pointing to their subscriptions: %s" % context_sqs)

    sqs = core.boto_sqs_conn(region)
    sns = core.boto_sns_conn(region)
    for queue_name in context_sqs:
        LOG.info('Setup of SQS queue %s', queue_name, extra={'stackname': stackname})
        queue = sqs.lookup(queue_name)
        subscriptions = context_sqs[queue_name]
        assert isinstance(subscriptions, list), ("Not a list of topics: %s" % subscriptions)
        for topic_name in subscriptions:
            LOG.info('Subscribing %s to SNS topic %s', queue_name, topic_name, extra={'stackname': stackname})
            # idempotent, works as lookup
            # risky, may subscribe to a typo-filled topic name like 'aarticles'
            # there is no boto method to lookup a topic
            topic_lookup = sns.create_topic(topic_name)
            topic_arn = topic_lookup['CreateTopicResponse']['CreateTopicResult']['TopicArn']
            # deals with both subscription and IAM policy
            response = sns.subscribe_sqs_queue(topic_arn, queue)
            assert 'SubscribeResponse' in response
            assert 'SubscribeResult' in response['SubscribeResponse']
            assert 'SubscriptionArn' in response['SubscribeResponse']['SubscribeResult']
            subscription_arn = response['SubscribeResponse']['SubscribeResult']['SubscriptionArn']
            LOG.info('Setting RawMessageDelivery of subscription %s', subscription_arn, extra={'stackname': stackname})
            sns.set_raw_subscription_attribute(subscription_arn)

def setup_s3(stackname, context_s3, region, account_id):
    """
    Connects S3 buckets (existing or created by Cloud Formation) to SQS queues
    that will be notified of files being added there.

    This function adds also a Statement to the Policy of the involved queue so that this bucket can send messages to it.
    """
    assert isinstance(context_s3, dict), ("Not a dictionary of bucket names pointing to their configurations: %s" % context_s3)

    s3 = core.boto_s3_conn(region)
    for bucket_name in context_s3:
        LOG.info('Setting NotificationConfiguration for bucket %s', bucket_name, extra={'stackname': stackname})
        if 'sqs-notifications' in context_s3[bucket_name]:
            queues = context_s3[bucket_name]['sqs-notifications']

            queue_configurations = _queue_configurations(stackname, queues, bucket_name, region)
            LOG.info('QueueConfigurations are %s', queue_configurations, extra={'stackname': stackname})
            s3.put_bucket_notification_configuration(
                Bucket=bucket_name,
                NotificationConfiguration={
                    'QueueConfigurations': queue_configurations
                }
            )

def _queue_configurations(stackname, queues, bucket_name, region):
    """Builds the QueueConfigurations element for configuring notifications coming from bucket_name"""
    assert isinstance(queues, dict), ("Not a dictionary of queue names pointing to their notification specifications: %s" % queues)

    queue_configurations = []
    for queue_name in queues:
        notification_specification = queues[queue_name]
        assert isinstance(notification_specification, dict), ("Not a dictionary of queue specification parameters: %s" % queues)
        queue_arn = _setup_s3_to_sqs_policy(stackname, queue_name, bucket_name, region)
        queue_configurations.append(_sqs_notification_configuration(queue_arn, notification_specification))
    return queue_configurations

def _setup_s3_to_sqs_policy(stackname, queue_name, bucket_name, region):
    """Loads the policy of queue_name, and adds a statement to let bucket_name
    notify to it"""
    # the only way to make this work is to add a new policy
    # statement for each of the buckets
    # - you cannot filter the AWS account by Principal (for some unknown reason)
    # - you also cannot specify arn:aws:s3:*:{account_id}:* as the SourceArn (for some other unknown reason)
    # Failure to set the right policy here won't make this call fail;
    # instead, you will get an error when trying to set the
    # NotificationConfiguration on the bucket later.
    # This also has to be idempotent... basically we are reiventing CloudFormation in Python because they don't support creating a bucket, a queue and their connection in a single template (you have to create a template without the linkage and then edit it and update it.)
    sqs = core.boto_sqs_conn(region)
    queue = sqs.lookup(queue_name)
    attributes = sqs.get_queue_attributes(queue, 'Policy')
    if 'Policy' in attributes:
        policy = json.loads(attributes['Policy'])
    else:
        policy = {
            "Version": "2012-10-17",
            "Id": queue.arn + "/SQSDefaultPolicy",
            "Statement": []
        }
    statement_to_upsert = {
        "Sid": queue.arn + "/SendMessageFromBucket/%s" % bucket_name,
        "Effect": "Allow",
        "Principal": '*',
        "Action": "SQS:SendMessage",
        "Resource": queue.arn,
        "Condition": {
            "ArnLike": {
                "aws:SourceArn": "arn:aws:s3:*:*:%s" % bucket_name,
            }
        },
    }
    if statement_to_upsert not in policy['Statement']:
        policy['Statement'].append(statement_to_upsert)
    policy_json = json.dumps(policy)
    LOG.info('Setting Policy for queue %s to allow SendMessage: %s', queue_name, policy_json, extra={'stackname': stackname})
    sqs.set_queue_attribute(queue, 'Policy', policy_json)
    return queue.arn

def _sqs_notification_configuration(queue_arn, notification_specification):
    filter_rules = []
    if 'prefix' in notification_specification:
        filter_rules.append({
            'Name': 'prefix',
            'Value': notification_specification['prefix'],
        })
    if 'suffix' in notification_specification:
        filter_rules.append({
            'Name': 'suffix',
            'Value': notification_specification['suffix'],
        })

    queue_configuration = {
        'QueueArn': queue_arn,
        'Events': [
            's3:ObjectCreated:*',
        ],
    }
    if filter_rules:
        queue_configuration['Filter'] = {
            'Key': {
                'FilterRules': filter_rules
            }
        }

    return queue_configuration

def update_s3_stack(stackname, **kwargs):
    pdata = project_data_for_stackname(stackname)
    if not pdata['aws']['s3']:
        return
    context = context_handler.load_context(stackname)

    if 's3' not in context:
        # old instance of the stack that hasn't any S3 buckets
        return

    setup_s3(stackname, context['s3'], pdata['aws']['region'], pdata['aws']['account_id'])


#
#  attached stack resources, ec2 data
#

@core.requires_active_stack
def stack_resources(stackname):
    "returns a list of resources provisioned by the given stack"
    return connect_aws_with_stack(stackname, 'cfn').describe_stack_resources(stackname)

def ec2_instance_data(stackname):
    "returns the ec2 instance data from the first ec2 instance the stack has"
    assert stackname, "stackname must be valid, not None"
    ec2 = first([r for r in stack_resources(stackname) if r.resource_type == "AWS::EC2::Instance"])
    conn = connect_aws_with_stack(stackname, 'ec2')
    return conn.get_only_instances([ec2.physical_resource_id])[0]

@cached
def master_data(region):
    "returns the ec2 instance data for the master-server"
    stackname = core.find_master(region)
    assert stackname, ("Cannot find the master in region %s" % region)
    return ec2_instance_data(stackname)

def master(region, key):
    return getattr(master_data(region), key)

#
# bootstrap stack
#

def current_template(stackname):
    conn = connect_aws_with_stack(stackname, 'cfn')
    return json.loads(conn.get_template(stackname)['GetTemplateResponse']['GetTemplateResult']['TemplateBody'])

def update_template(stackname, template):
    conn = connect_aws_with_stack(stackname, 'cfn')
    parameters = []
    pdata = project_data_for_stackname(stackname)
    if pdata['aws']['ec2']:
        parameters.append(('KeyName', stackname))
    try:
        conn.update_stack(stackname, json.dumps(template), parameters=parameters)
    except BotoServerError as ex:
        if ex.message == 'No updates are to be performed.':
            return
        raise

    def stack_is_updating():
        return not core.stack_is(stackname, ['UPDATE_COMPLETE'], terminal_states=['UPDATE_ROLLBACK_COMPLETE'])
    call_while(stack_is_updating, interval=2, timeout=7200, update_msg="waiting for template of %s to be updated" % stackname, done_msg="template of %s is in state UPDATE_COMPLETE" % stackname)

@core.requires_active_stack
def template_info(stackname):
    "returns some useful information about the given stackname as a map"
    conn = connect_aws_with_stack(stackname, 'cfn')
    data = conn.describe_stacks(stackname)[0].__dict__
    data['outputs'] = reduce(utils.conj, map(lambda o: {o.key: o.value}, data['outputs']))
    return utils.exsubdict(data, ['connection', 'parameters'])

def write_environment_info(stackname, overwrite=False):
    """Looks for /etc/cfn-info.json and writes one if not found.
    Must be called with an active stack connection.

    This gives Salt the outputs available at stack creation, but that were not
    available at template compilation time.
    """
    if not files.exists("/etc/cfn-info.json") or overwrite:
        LOG.info('no cfn outputs found or overwrite=True, writing /etc/cfn-info.json ...')
        infr_config = utils.json_dumps(template_info(stackname))
        return put(StringIO(infr_config), "/etc/cfn-info.json", use_sudo=True)
    LOG.debug('cfn outputs found, skipping')
    return []

#
#
#

@core.requires_active_stack
def update_stack(stackname, service_list=None, **kwargs):
    """updates the given stack. if a list of services are provided (s3, ec2, sqs, etc)
    then only those services will be updated"""
    service_update_fns = OrderedDict([
        ('ec2', update_ec2_stack),
        ('s3', update_s3_stack),
        ('sqs', update_sqs_stack)
    ])
    if not service_list:
        service_list = service_update_fns.keys()
    ensure(utils.iterable(service_list), "cannot iterate over given service list %r" % service_list)

    [fn(stackname, **kwargs) for fn in subdict(service_update_fns, service_list).values()]

def upload_master_builder_key(key):
    private_key = "/root/.ssh/id_rsa"
    try:
        # NOTE: overwrites any existing master key on machine being updated
        operations.put(local_path=key, remote_path=private_key, use_sudo=True)
    finally:
        key.close()

def download_master_builder_key(stackname):
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    master_stack = core.find_master(region)
    private_key = "/root/.ssh/id_rsa"
    fh = StringIO()
    with stack_conn(master_stack):
        operations.get(remote_path=private_key, local_path=fh, use_sudo=True)
    return fh

def download_master_configuration(master_stack):
    fh = StringIO()
    with stack_conn(master_stack, username=BOOTSTRAP_USER):
        operations.get(remote_path='/etc/salt/master.template', local_path=fh, use_sudo=True)
    fh.seek(0)
    return fh

def expand_master_configuration(master_configuration_template, formulas=None):
    "reads a /etc/salt/master type file in as YAML and returns a processed python dictionary"
    cfg = core_utils.ordered_load(master_configuration_template)

    if not formulas:
        formulas = project.known_formulas() # *all* formulas

    def basename(formula):
        return re.sub('-formula$', '', os.path.basename(formula))
    formula_path = '/opt/formulas/%s/salt/'

    cfg['file_roots']['base'] = \
        ["/opt/builder-private/salt/"] + \
        [formula_path % basename(f) for f in formulas] + \
        ["/opt/formulas/builder-base/"]
    cfg['pillar_roots']['base'] = ["/opt/builder-private/pillar"]
    # dealt with at the infrastructural level
    cfg['interface'] = '0.0.0.0'
    return cfg

def upload_master_configuration(master_stack, master_configuration):
    with stack_conn(master_stack, username=BOOTSTRAP_USER):
        operations.put(local_path=master_configuration, remote_path='/etc/salt/master', use_sudo=True)

def update_ec2_stack(stackname, concurrency=None, formula_revisions=None, **kwargs):
    """installs/updates the ec2 instance attached to the specified stackname.

    Once AWS has finished creating an EC2 instance for us, we need to install
    Salt and get it talking to the master server. Salt comes with a bootstrap
    script that can be downloaded from the web and then very conveniently
    installs it's own dependencies. Once Salt is installed we give it an ID
    (the given `stackname`), the address of the master server """
    ctx = context_handler.load_context(stackname)
    pdata = ctx['project']
    # backward compatibility: old instances may not have 'ec2' key
    # consider it true if missing, as newer stacks e.g. bus--prod
    # would have it explicitly set to False
    default_ec2 = {'masterless': False, 'cluster-size': 1}
    ec2 = pdata['aws'].get('ec2', default_ec2)
    if not ec2:
        return
    if ec2 is True:
        ec2 = default_ec2
    region = pdata['aws']['region']
    is_master = core.is_master_server_stack(stackname)
    is_masterless = ec2.get('masterless', False)

    master_builder_key = None
    if is_masterless:
        master_builder_key = download_master_builder_key(stackname)

    def _update_ec2_node():
        # upload private key if not present remotely
        if not files.exists("/root/.ssh/id_rsa", use_sudo=True):
            # if it also doesn't exist on the filesystem, die horribly.
            # regular updates shouldn't have to deal with this.
            pem = stack_pem(stackname, die_if_doesnt_exist=True)
            put(pem, "/root/.ssh/id_rsa", use_sudo=True)

        # write out environment config (/etc/cfn-info.json) so Salt can read CFN outputs
        write_environment_info(stackname, overwrite=True)

        salt_version = pdata['salt']
        install_master_flag = str(is_master or is_masterless).lower() # ll: 'true'
        master_ip = master(region, 'private_ip_address')

        build_vars = bvars.read_from_current_host()
        minion_id = build_vars.get('nodename', stackname)
        run_script('bootstrap.sh', salt_version, minion_id, install_master_flag, master_ip)

        if is_masterless:
            # order is important.
            formula_list = ' '.join(pdata.get('formula-dependencies', []) + [pdata['formula-repo']])
            # to init the builder-private formula, the masterless instance needs
            # the master-builder key
            upload_master_builder_key(master_builder_key)
            envvars = {
                'BUILDER_TOPFILE': os.environ.get('BUILDER_TOPFILE', '')
            }
            # Vagrant's equivalent is 'init-vagrant-formulas.sh'
            run_script('init-formulas.sh', formula_list, pdata['private-repo'], **envvars)

            # second pass to optionally update formulas to specific revisions
            for repo, formula, revision in formula_revisions or []:
                run_script('update-master-formula.sh', repo, formula, revision)

        if is_master:
            # it is possible to be a masterless master server
            builder_private_repo = pdata['private-repo']
            all_formulas = project.known_formulas()
            run_script('init-master.sh', stackname, builder_private_repo, ' '.join(all_formulas))
            master_configuration_template = download_master_configuration(stackname)
            master_configuration = expand_master_configuration(master_configuration_template, all_formulas)
            upload_master_configuration(stackname, yaml_dump(master_configuration))
            run_script('update-master.sh', stackname, builder_private_repo)
            put_script('update-master.sh', '/opt/update-master.sh')

        # this will tell the machine to update itself
        run_script('highstate.sh')

    stack_all_ec2_nodes(stackname, _update_ec2_node, username=BOOTSTRAP_USER, concurrency=concurrency)

@core.requires_stack_file
def delete_stack_file(stackname):
    try:
        core.describe_stack(stackname) # triggers exception if NOT exists
        LOG.warning('stack %r still exists, refusing to delete stack files. delete active stack first.', stackname)
        return
    except BotoServerError as ex:
        if not ex.message.endswith('does not exist'):
            LOG.exception("unhandled exception attempting to confirm if stack %r exists", stackname)
            raise
    ext_list = [
        ".pem",
        ".pub",
        ".json",
        ".yaml", # yaml files are now deprecated
    ]
    paths = [join(config.STACK_DIR, stackname + ext) for ext in ext_list]
    paths = filter(os.path.exists, paths)

    def _unlink(path):
        os.unlink(path)
        return not os.path.exists(path)
    return dict(zip(paths, map(_unlink, paths)))

def remove_minion_key(stackname):
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    master_stack = core.find_master(region)
    with stack_conn(master_stack):
        sudo("rm -f /etc/salt/pki/master/minions/%s--*" % stackname)

def delete_stack(stackname):
    try:
        connect_aws_with_stack(stackname, 'cfn').delete_stack(stackname)

        def is_deleting(stackname):
            try:
                return core.describe_stack(stackname).stack_status in ['DELETE_IN_PROGRESS']
            except BotoServerError as err:
                if err.message.endswith('does not exist'):
                    return False
                raise # not sure what happened, but we're not handling it here. die.
        utils.call_while(partial(is_deleting, stackname), timeout=3600, update_msg='Waiting for AWS to finish deleting stack ...')
        # TODO: call remove_minion_key()? (from master server)
        keypair.delete_keypair(stackname)
        delete_stack_file(stackname)
        delete_dns(stackname)

        LOG.info("stack %r deleted", stackname)
    except BotoServerError as err:
        LOG.exception("[%s: %s] %s (request-id: %s)", err.status, err.reason, err.message, err.request_id)
