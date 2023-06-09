"""Logic for provisioning and bootstrapping an automatically
created Cloudformation template.

The "stackname" parameter these functions take is the name of the cfn template
without the extension."""

import os, json, re
from os.path import join
from collections import OrderedDict
from datetime import datetime
from . import utils, config, bvars, core, context_handler, project, cloudformation, terraform, sns as snsmod, command
from .context_handler import only_if
from .core import stack_all_ec2_nodes, project_data_for_stackname, stack_conn
from .utils import first, ensure, subdict, yaml_dumps, lmap
from .lifecycle import delete_dns
from .config import BOOTSTRAP_USER, WHOAMI, CI_USER
from .command import remote_sudo, remote_file_exists, remote_listfiles
import backoff
import botocore
from kids.cache import cache as cached
from collections.abc import Iterable

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
    return command.put(local_script, remote_script)

def put_script(script_filename, remote_script):
    """uploads a script for `config.SCRIPTS_PATH` in remote_script location, making it executable
    WARN: assumes you are connected to a stack"""
    temporary_script = _put_temporary_script(script_filename)
    remote_sudo("mv %s %s && chmod +x %s" % (temporary_script, remote_script, remote_script))

@backoff.on_exception(backoff.expo, command.NetworkError, max_time=60)
def run_script(script_filename, *script_params, **environment_variables):
    """uploads a script for `config.SCRIPTS_PATH` and executes it in the /tmp dir with given params.
    script is run as the root user via sudo.
    WARN: assumes you are connected to a stack"""
    start = datetime.now()
    remote_script = _put_temporary_script(script_filename)

    def escape_string_parameter(parameter):
        return "'%s'" % parameter

    env_string = ['%s=%s' % (k, v) for k, v in environment_variables.items()]
    cmd = ["/bin/bash", remote_script] + lmap(escape_string_parameter, list(script_params))
    result = remote_sudo(" ".join(env_string + cmd))
    retval = result['return_code']
    remote_sudo("rm " + remote_script) # remove the script after executing it
    end = datetime.now()
    LOG.info("Executed script %s in %2.4f seconds", script_filename, (end - start).total_seconds())
    return retval

def clean_stack_for_ami():
    return run_script("clean-stack-for-ami.sh")


#
# provision stack
#

def create_stack(stackname):
    "transforms templates stored on the filesystem into real resources (AWS via CloudFormation, Terraform)"

    LOG.info('creating stack %r', stackname)
    try:
        context = context_handler.load_context(stackname)
        cloudformation.bootstrap(stackname, context)
        terraform.bootstrap(stackname, context)
        # setup various resources after creation, where necessary
        setup_ec2(stackname, context)
        return True

    except KeyboardInterrupt:
        LOG.debug("caught keyboard interrupt, cancelling...")
        return False


@only_if('ec2')
def setup_ec2(stackname, context):
    def _setup_ec2_node():
        def is_resourcing():
            try:
                # we have an issue where the stack is created, but the security group
                # hasn't been attached or ssh isn't running yet and we can't get in.
                # this waits until:
                # - bootstrap user exists and we can access it through SSH
                # - cloud-init has finished running
                #       otherwise we may be missing /etc/apt/source.list, which is generated on boot
                #       https://www.digitalocean.com/community/questions/how-to-make-sure-that-cloud-init-finished-running
                return not remote_file_exists(join('/home', BOOTSTRAP_USER, ".ssh/authorized_keys")) \
                    or not remote_file_exists('/var/lib/cloud/instance/boot-finished')
            except command.NetworkError:
                LOG.debug("failed to connect to server ...")
                return True
        utils.call_while(is_resourcing, interval=config.AWS_POLLING_INTERVAL, update_msg='Waiting for /home/ubuntu to be detected ...')

    stack_all_ec2_nodes(stackname, _setup_ec2_node, username=BOOTSTRAP_USER)

def remove_topics_from_sqs_policy(policy, topic_arns):
    """Removes statements from an SQS policy.
    These statements are created by boto's subscribe_sqs_queue()"""

    def for_unsubbed_topic(statement):
        # `statement` looks like:
        # {u'Statement': [{u'Action': u'SQS:SendMessage',
        #   u'Condition': {u'StringLike': {u'aws:SourceArn': u'arn:aws:sns:us-east-1:512686554592:bus-profiles--end2end'}},
        #   u'Effect': u'Allow',
        #   u'Principal': {u'AWS': u'*'},
        #   u'Resource': u'arn:aws:sqs:us-east-1:512686554592:annotations--end2end',
        #   u'Sid': u'5a1770151e27027c1f43d7f3c968fc10'}],
        # u'Version': u'2008-10-17'}
        return statement.get('Condition', {}).get('StringLike', {}).get('aws:SourceArn') in topic_arns

    policy['Statement'] = [s for s in policy.get('Statement', []) if not for_unsubbed_topic(s)]
    if policy['Statement']:
        return policy

def unsub_sqs(stackname, context_sqs, region, dry_run=False):
    all_subscriptions = core.all_sns_subscriptions(region, stackname)

    # lsh@2022-08-30, issue#6016: detect multiple subscriptions and prune them.
    # don't know how it happened but we have cases where a project has multiple subscriptions to the same topic.
    # this would mean multiple duplicate notifications.

    # group subscriptions by Topic so we detect duplicates below.
    sub_groups = utils.mkidx(lambda sub: sub['Topic'], all_subscriptions)

    unsub_map = {}
    for queue_name, ctx_subscription_list in context_sqs.items():
        # compare project subscriptions to those actively subscribed to (`all_subscriptions`)
        unsub_map[queue_name] = [sub for sub in all_subscriptions if sub['Topic'] not in ctx_subscription_list]

        # lsh@2022-08-30, issue#6016: detect multiple subscriptions and prune them.
        # look for subscription in sub groups with >1 subs and ensure it gets removed.
        for sub in all_subscriptions:
            topic = sub['Topic']
            if topic in sub_groups and len(sub_groups[topic]) > 1:
                msg_list = [t['SubscriptionArn'].split(':')[-1] for t in sub_groups[topic]]
                LOG.warning("multiple SQS subscriptions to the SNS topic %r found: %s" % (topic, msg_list))
                unsub_map[queue_name].append(sub_groups[topic].pop())

    # 'permissions' here is more like 'policy': what to do (send a message) when receiving a message from a source (SNS)
    # we strip these and re-add them on each update.
    permission_map = {queue_name: [sub['TopicArn'] for sub in sub_list] for queue_name, sub_list in unsub_map.items()}

    if dry_run:
        return unsub_map, permission_map

    sns = core.boto_client('sns', region)
    for sub in utils.shallow_flatten(unsub_map.values()):
        LOG.info("Unsubscribing %s from %s", sub['Topic'], stackname)
        sns.unsubscribe(SubscriptionArn=sub['SubscriptionArn'])

    sqs = core.boto_resource('sqs', region)
    for queue_name, topic_arns in permission_map.items():
        # not an atomic update, but there's no other way to do it
        queue = sqs.get_queue_by_name(QueueName=queue_name)
        policy = json.loads(queue.attributes.get('Policy', '{}'))
        LOG.info("Saving new Policy for %s removing %s (%s)", queue_name, topic_arns, policy)
        new_policy = remove_topics_from_sqs_policy(policy, topic_arns)
        new_policy_json = json.dumps(new_policy) if new_policy else ''

        try:
            LOG.info("Existing policy: %s", queue.attributes.get('Policy'))
            queue.set_attributes(Attributes={'Policy': new_policy_json})
        except botocore.exceptions.ClientError as ex:
            msg = "uncaught boto exception updating policy for queue %r: %s" % (queue_name, new_policy_json)
            # TODO: `extra` is logged but not rendered so are effectively lost
            LOG.exception(msg, extra={'response': ex.response, 'permission_map': permission_map.items()})
            raise

    return unsub_map, permission_map

def sub_sqs(stackname, context_sqs, region):
    """
    Connects SQS queues created by Cloud Formation to SNS topics where
    necessary, adding both the subscription and the IAM policy to let the SNS
    topic write to the queue
    """
    ensure(isinstance(context_sqs, dict), "Not a dictionary of queues pointing to their subscriptions: %s" % context_sqs)

    sqs = core.boto_resource('sqs', region)
    sns_client = core.boto_client('sns', region)

    for queue_name, subscription_list in context_sqs.items():
        LOG.info('Setup of SQS queue %s', queue_name, extra={'stackname': stackname})
        ensure(isinstance(subscription_list, list), "Not a list of topics: %s" % subscription_list)

        queue = sqs.get_queue_by_name(QueueName=queue_name)
        for topic_name in subscription_list:
            LOG.info('Subscribing %s to SNS topic %s', queue_name, topic_name, extra={'stackname': stackname})

            # idempotent, works as lookup
            # risky, may subscribe to a typo-filled topic name like 'aarticles'
            # there is no boto method to lookup a topic
            # lsh@2021-11-02: there is now a boto method to lookup topics:
            # - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#SNS.Client.list_topics
            topic_lookup = sns_client.create_topic(Name=topic_name) # idempotent
            topic_arn = topic_lookup['TopicArn']

            # deals with both subscription and IAM policy
            # - http://boto.cloudhackers.com/en/latest/ref/sns.html#boto.sns.SNSConnection.subscribe_sqs_queue
            # - https://github.com/boto/boto/blob/develop/boto/sns/connection.py#L322
            #response = sns.subscribe_sqs_queue(topic_arn, queue)
            # WARN: doesn't do all of the above in boto3
            #response = sns.subscribe(TopicArn=topic_arn, Protocol='sqs', Endpoint=queue.attributes['QueueArn'])
            response = snsmod.subscribe_sqs_queue(sns_client, topic_arn, queue)

            ensure('SubscriptionArn' in response, "failed to find ARN of new subscription")
            subscription_arn = response['SubscriptionArn']
            LOG.info('Setting RawMessageDelivery of subscription %s', subscription_arn, extra={'stackname': stackname})
            sns_client.set_subscription_attributes(SubscriptionArn=subscription_arn, AttributeName='RawMessageDelivery', AttributeValue='true')

@only_if('sqs')
@core.requires_active_stack
def update_sqs_stack(stackname, context, **kwargs):
    region = context['aws']['region']
    unsub_sqs(stackname, context['sqs'], region)
    sub_sqs(stackname, context['sqs'], region)

@only_if('s3')
@core.requires_active_stack
def update_s3_stack(stackname, context, **kwargs):
    """
    Connects S3 buckets (existing or created by Cloud Formation) to SQS queues
    that will be notified of files being added there.

    This function adds also a Statement to the Policy of the involved queue so that this bucket can send messages to it.
    """
    context_s3 = context['s3']
    region = context['aws']['region']

    ensure(isinstance(context_s3, dict), "Not a dictionary of bucket names pointing to their configurations: %s" % context_s3)

    s3 = core.boto_client('s3', region)
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
    ensure(isinstance(queues, dict), "Not a dictionary of queue names pointing to their notification specifications: %s" % queues)

    queue_configurations = []
    for queue_name in queues:
        notification_specification = queues[queue_name]
        ensure(isinstance(notification_specification, dict), "Not a dictionary of queue specification parameters: %s" % queues)
        queue_arn = _setup_s3_to_sqs_policy(stackname, queue_name, bucket_name, region)
        queue_configurations.append(_sqs_notification_configuration(queue_arn, notification_specification))
    return queue_configurations

def _setup_s3_to_sqs_policy(stackname, queue_name, bucket_name, region):
    """Loads the policy of queue_name, and adds a statement to let bucket_name
    send notifications to it."""
    # the only way to make this work is to add a new policy
    # statement for each of the buckets
    # - you cannot filter the AWS account by Principal (for some unknown reason)
    # - you also cannot specify arn:aws:s3:*:{account_id}:* as the SourceArn (for some other unknown reason)
    # Failure to set the right policy here won't make this call fail;
    # instead, you will get an error when trying to set the
    # NotificationConfiguration on the bucket later.
    # This also has to be idempotent... basically we are reiventing CloudFormation in Python because they don't support creating a bucket, a queue and their connection in a single template (you have to create a template without the linkage and then edit it and update it.)
    queue = core.boto_resource('sqs', region).get_queue_by_name(QueueName=queue_name)
    policy = queue.attributes.get('Policy')
    if policy:
        policy = json.loads(policy)
    else:
        policy = {
            "Version": "2012-10-17",
            "Id": queue.attributes['QueueArn'] + "/SQSDefaultPolicy",
            "Statement": []
        }

    queue_arn = queue.attributes['QueueArn']
    statement_to_upsert = {
        "Sid": queue_arn + "/SendMessageFromBucket/%s" % bucket_name,
        "Effect": "Allow",
        "Principal": '*',
        "Action": "SQS:SendMessage",
        "Resource": queue_arn,
        "Condition": {
            "ArnLike": {
                "aws:SourceArn": "arn:aws:s3:*:*:%s" % bucket_name,
            }
        }
    }
    if statement_to_upsert not in policy['Statement']:
        policy['Statement'].append(statement_to_upsert)
    policy_json = json.dumps(policy)
    LOG.info('Setting Policy for queue %s to allow SendMessage: %s', queue_name, policy_json, extra={'stackname': stackname})
    queue.set_attributes(Attributes={'Policy': policy_json})
    return queue_arn

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


#
#  attached stack resources, ec2 data
#

@cached
def master_data(region):
    "returns the ec2 instance data for the master-server"
    stackname = core.find_master(region)
    master_inst = first(core.find_ec2_instances(stackname))
    return master_inst.meta.data

def master(region, key):
    return master_data(region)[key]

#
#
#

def update_stack(stackname, service_list=None, **kwargs):
    """updates the given stack. if a list of services are provided (s3, ec2, sqs, etc)
    then only those services will be updated"""
    # TODO: partition away at least ec2
    # Has too many responsibilities:
    #    - ec2: deploys
    #    - s3, sqs, ...: infrastructure updates
    service_update_fns = OrderedDict([
        ('ec2', (update_ec2_stack, ['concurrency', 'formula_revisions', 'dry_run'])),
        ('s3', (update_s3_stack, [])),
        ('sqs', (update_sqs_stack, [])),
    ])
    service_list = service_list or service_update_fns.keys()
    ensure(isinstance(service_list, Iterable), "cannot iterate over given service list %r" % service_list)
    context = context_handler.load_context(stackname)
    for servicename, (fn, fn_kwarg_args) in subdict(service_update_fns, service_list).items():
        actual_arguments = subdict(kwargs, fn_kwarg_args)
        fn(stackname, context, **actual_arguments)

def upload_master_builder_key(key):
    old_public_key = "/root/.ssh/id_rsa.pub"
    private_key = "/root/.ssh/id_rsa"
    LOG.info("upload master builder key to %s", private_key)
    try:
        # NOTE: overwrites any existing master key on machine being updated
        command.put(local_path=key, remote_path=private_key, use_sudo=True)
        remote_sudo("rm -f %s && chown root:root %s && chmod 600 %s" % (old_public_key, private_key, private_key))
    finally:
        key.close()

def download_master_builder_key(stackname):
    pdata = project_data_for_stackname(stackname)
    region = pdata['aws']['region']
    master_stack = core.find_master(region)
    private_key = "/root/.ssh/id_rsa"
    with stack_conn(master_stack):
        label = "master builder key %s:%s" % (master_stack, private_key)
        return command.get(private_key, use_sudo=True, return_stream=True, label=label)

def download_master_configuration(master_stack):
    with stack_conn(master_stack, username=BOOTSTRAP_USER):
        return command.get('/etc/salt/master.template', use_sudo=True, return_stream=True)

def expand_master_configuration(master_configuration_template, formulas=None):
    "reads a /etc/salt/master type file in as YAML and returns a processed python dictionary"
    cfg = utils.yaml_load(master_configuration_template)

    if not formulas:
        formulas = project.known_formulas() # *all* formulas

    def basename(formula):
        return re.sub('-formula$', '', os.path.basename(formula))
    formula_path = '/opt/formulas/%s/salt/'

    cfg['file_roots']['base'] = \
        ["/opt/builder-private/salt/"] + \
        ["/opt/builder-configuration/salt/"] + \
        [formula_path % basename(f) for f in formulas] + \
        ["/opt/formulas/builder-base/"]
    cfg['pillar_roots']['base'] = \
        ["/opt/builder-private/pillar"] + \
        ["/opt/builder-configuration/pillar"]
    # dealt with at the infrastructural level
    cfg['interface'] = '0.0.0.0'
    return cfg

def upload_master_configuration(master_stack, master_configuration_data):
    with stack_conn(master_stack, username=BOOTSTRAP_USER):
        command.put_data(master_configuration_data, remote_path='/etc/salt/master', use_sudo=True)

@only_if('ec2')
@core.requires_active_stack
def update_ec2_stack(stackname, context, concurrency=None, formula_revisions=None, dry_run=False):
    """installs/updates the ec2 instance attached to the specified stackname.

    Once AWS has finished creating an EC2 instance for us, we need to install
    Salt and get it talking to the master server. Salt comes with a bootstrap
    script that can be downloaded from the web and then very conveniently
    installs it's own dependencies. Once Salt is installed we give it an ID
    (the given `stackname`), the address of the master server """

    # backward compatibility: old instances may not have 'ec2' key
    # consider it true if missing, as newer stacks e.g. bus--prod
    # would have it explicitly set to False
    default_ec2 = {'masterless': False, 'cluster-size': 1}
    ec2 = context.get('ec2', default_ec2)

    # TODO: check if any active stacks still have ec2: True in their context
    # and refresh their context then remove this check
    if ec2 is True:
        ec2 = default_ec2

    region = context['aws']['region']
    is_master = core.is_master_server_stack(stackname)
    is_masterless = ec2.get('masterless', False)

    master_builder_key = None
    if is_masterless:
        master_builder_key = download_master_builder_key(stackname)

    fkeys = ['formula-repo', 'formula-dependencies', 'private-repo', 'configuration-repo']
    fdata = subdict(context['project'], fkeys)

    def _update_ec2_node():
        # write out environment config (/etc/cfn-info.json) so Salt can read CFN outputs
        core.write_environment_info(stackname, overwrite=True)

        # bit of a hack, but project config merging doesn't apply to top-level values
        # in this case we look for an alternate salt version under a project's 'ec2' section
        salt_version = context['project']['salt']
        alt_salt_version = context['ec2'].get('salt')

        # and we only use it if we're going masterless
        if alt_salt_version and is_masterless:
            salt_version = alt_salt_version

        install_master_flag = str(is_master or is_masterless).lower() # "true"

        build_vars = bvars.read_from_current_host()
        minion_id = build_vars.get('nodename', stackname)
        master_ip = build_vars.get('ec2', {}).get('master_ip', master(region, 'PrivateIpAddress'))
        grains = {
            'project': context['project_name'],
        }
        environment_vars = {('grain_%s' % k): v for k, v in grains.items()}
        run_script('bootstrap.sh', salt_version, minion_id, install_master_flag, master_ip, **environment_vars)

        if is_masterless:
            # order is important.
            formula_list = ' '.join(fdata.get('formula-dependencies', []) + [fdata['formula-repo']])
            # to init the builder-private formula, the masterless instance needs
            # the master-builder key
            upload_master_builder_key(master_builder_key)
            envvars = {
                'BUILDER_TOPFILE': config.ENV['BUILDER_TOPFILE']
            }

            # Vagrant's equivalent is 'init-vagrant-formulas.sh'
            run_script(
                'init-masterless-formulas.sh',
                formula_list,
                fdata['private-repo'],
                fdata['configuration-repo'],
                **envvars
            )

            # second pass to optionally update formulas to specific revisions
            for repo, formula, revision in formula_revisions or []:
                run_script('update-masterless-formula.sh', repo, formula, revision)

        if is_master:
            # it is possible to be a masterless master server
            builder_private_repo = fdata['private-repo']
            builder_configuration_repo = fdata['configuration-repo']
            all_formulas = project.known_formulas()
            run_script('init-master.sh', stackname, builder_private_repo, builder_configuration_repo, ' '.join(all_formulas))
            master_configuration_template = download_master_configuration(stackname)
            master_configuration = expand_master_configuration(master_configuration_template, all_formulas)
            upload_master_configuration(stackname, yaml_dumps(master_configuration))
            run_script('update-master.sh', stackname, builder_private_repo)
            # TODO: I suspect this should be removed because the master-server must be updated through a builder command e.g. so that it adds any new formulas that come from the project/ definitions
            put_script('update-master.sh', '/opt/update-master.sh')

        # anything other than '--dry-run' and '--no-color' essentially
        highstate_dry_run = "--dry-run" if dry_run else "--no-dry-run"
        coloured_output = "--no-color" if WHOAMI == CI_USER else "--yes-color"
        run_script('highstate.sh', highstate_dry_run, coloured_output)

    stack_all_ec2_nodes(stackname, _update_ec2_node, username=BOOTSTRAP_USER, concurrency=concurrency)

# TODO: bootstrap.py may not be best place for this
def master_minion_keys(master_stackname, group_by_stackname=True):
    "returns a list of paths to minion keys on given master stack, optionally grouped by stackname"
    # all paths
    with stack_conn(master_stackname):
        master_stack_key_paths = remote_listfiles("/etc/salt/pki/master/minions/", use_sudo=True)
    if not group_by_stackname:
        return master_stack_key_paths
    # group by stackname. stackname is created by stripping node information off the end.
    # not all keys will have node information! in these case, we just want the first two 'bits'

    def keyfn(p):
        return "--".join(core.parse_stackname(os.path.basename(p), all_bits=True)[:2])
    return utils.mkidx(keyfn, master_stack_key_paths)

# TODO: bootstrap.py may not be best place for this
def orphaned_keys(master_stackname):
    "returns a list of paths to keys on the master server that have no corresponding *active* cloudformation stack"
    region = core.find_region(master_stackname)
    # ['annotations--continuumtest', 'annotations--end2end', 'annotations--prod', 'anonymous--continuum', 'api-gateway--continuumtest', ...]
    active_cfn_stack_names = core.active_stack_names(region)
    grouped_key_files = master_minion_keys(master_stackname)
    missing_stacks = set(grouped_key_files.keys()).difference(active_cfn_stack_names)
    missing_paths = subdict(grouped_key_files, missing_stacks)
    return sorted(utils.shallow_flatten(missing_paths.values()))

# TODO: bootstrap.py may not be best place for this
def remove_all_orphaned_keys(master_stackname):
    with stack_conn(master_stackname):
        for path in orphaned_keys(master_stackname):
            fname = os.path.basename(path) # prevent accidental deletion of anything not a key
            remote_sudo("rm -f /etc/salt/pki/master/minions/%s" % fname)

# TODO what does stack destruction have to do with ec2 bootstrap?
# it can't be moved to core because of the `cloudformation` module dependency.
# we need something in buildercore/ that ties all these disparate things together
def destroy(stackname):
    # TODO: if context does not exist anymore on S3,
    # we could exit idempotently

    context = context_handler.load_context(stackname)
    terraform.destroy(stackname, context)
    cloudformation.destroy(stackname, context)

    # don't do this. requires master server access and would prevent regular users deleting stacks
    # core.remove_minion_key(stackname)
    delete_dns(stackname)

    context_handler.delete_context(stackname)
    LOG.info("stack %r deleted", stackname)
