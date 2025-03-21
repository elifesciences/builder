
"""
Marshalls a collection of project information together in to a dictionary called the `context`.

When an instance of a project is launched on AWS, we need to tweak things a bit with no
manual steps in some cases or with as few as possible in other cases.

Case 1: New, standardized environment
We launch journal--ci, a testing instance for the journal project within the `ci` environment.

Case 2: Ad-hoc instances
We launch journal--testsomething, a testing instance we will use to check something works as expected.

Case 3: Stack updates
We want to add an external volume to an EC2 instance to increase available space, so we partially update the CloudFormation template to create it.

"""
import json
import logging
import re
from collections import OrderedDict, namedtuple
from functools import partial

import botocore
import netaddr
from slugify import slugify

from . import cloudformation, config, context_handler, core, project, terraform, utils
from .utils import deepcopy, delkey, ensure, lmap, lookup, subdict

LOG = logging.getLogger(__name__)

# taken from:
# - https://developer.fastly.com/learning/concepts/shielding/#choosing-a-shield-location
FASTLY_AWS_REGION_SHIELDS = {
    'us-east-1': 'iad-va-us', # Ashburn (Metro)
    'us-east-2': 'mdw-il-us', # Ohio: Chicago
    'us-west-1': 'pao-ca-us', # Palo Alto
    'us-west-2': 'sea-wa-us', # Oregon: Seattle
    'ap-northeast-1': 'tyo-tokyo-jp', # Tokyo: Tokyo
    'ap-northeast-2': 'osaka-jp', # Osaka
    'ap-northeast-3': 'osaka-jp', # Osaka
    'ap-south-1': 'bom-mumbai-in', # Mumbai
    'ap-southeast-1': 'qpg-singapore-sg', # Singapore
    'ap-southeast-2': 'sydney-au', # Sydney : Sydney
    'ca-central-1': 'yyz-on-ca', # Canada (Central): Toronto
    'cn-north-1': 'hongkong-hk', # Beijing: Hong Kong
    'cn-northwest-1': 'hongkong-hk', # Ningxia: Hong Kong
    'eu-central-1': 'frankfurt-de', # Frankfurt: Frankfurt
    'eu-west-1': 'dub-dublin-ie', # Dublin
    'eu-west-2': 'london-uk', # London - LHR
    'eu-west-3': 'cdg-par-fr', # Paris: Paris
    'sa-east-1': 'gig-riodejaneiro-br', # Rio de Janeiro
}

def instance_alias(instance_id):
    """if an instance called FOO has an alias BAR, return BAR else `None`.

    Used in cases where the resource names generated with the `instance_id` are too long!
    for example, the `instance_id`:
        "pr-100-base-update"
        "pr-65-fresh-snsalt"
    may generate an S3 bucket name of:
        "pr-100-base-update-elife-bot-accepted-submission-cleaning-output"
        "pr-65-fresh-snsalt-elife-bot-accepted-submission-cleaning-output"
    that is 64 characters long when the maximum is 63.
    with an alias we can shorten that at the expense of this extra indirection."""
    if not isinstance(instance_id, str):
        return None

    # pr-*-base-update
    base_update_alias_regex = re.compile(r"pr-(?P<pr>\d+)-base-update")
    match = re.match(base_update_alias_regex, instance_id)
    if match:
        alias = "bu"
        pr_num = match.group('pr')
        return "pr-%s-%s" % (pr_num, alias) # "pr-123-bu"

    # pr-*-fresh-snsalt
    fresh_snsalt_alias_regex = re.compile(r"pr-(?P<pr>\d+)-fresh-snsalt")
    match = re.match(fresh_snsalt_alias_regex, instance_id)
    if match:
        alias = "fs"
        pr_num = match.group('pr')
        return "pr-%s-%s" % (pr_num, alias) # "pr-123-fs"

    # add further aliases here
    # ...

    return None

def parameterize(context):
    """certain property values in the project file are placeholders and are replaced with
    actual values from the *project instance context* at render time.
    These placeholders use standard Python string interpolation.
    For example: "{placeholder}" becomes "{placeholder}".format(placeholder=context['placeholder'])"""
    def wrapper(string):
        placeholders = {
            'instance': context['instance_id'],
            'instance-alias-or-instance': instance_alias(context['instance_id']) or context['instance_id']
        }
        return string.format(**placeholders)
    return wrapper

def hostname_struct(stackname):
    "returns a dictionary with convenient domain name information"

    pname, instance_id = core.parse_stackname(stackname)

    # lsh@2022-09-19: err, watch out here, boundaries between project and instance context
    # data have become blurry. func signature needs a stackname, implying a project *instance*,
    # but then we immediately load the raw project data and start pulling from there.

    pdata = project.project_data(pname)
    domain = pdata.get('domain')
    intdomain = pdata.get('intdomain')
    subdomain = pdata.get('subdomain')

    struct = {
        'domain': domain, # elifesciences.org
        'int_domain': intdomain, # elife.internal

        'subdomain': subdomain, # gateway

        'hostname': None, # temp.gateway

        'project_hostname': None, # gateway.elifesciences.org
        'int_project_hostname': None, # gateway.elife.internal

        'full_hostname': None, # gateway--temp.elifesciences.org
        'int_full_hostname': None, # gateway--temp.elife.internal
    }
    if not subdomain:
        # this project doesn't expect to be addressed
        # return immediately with what we do have
        return struct

    # removes any non-alphanumeric or hyphen characters
    instance_subdomain_fragment = re.sub(r'[^\w\-]', '', instance_id)
    hostname = instance_subdomain_fragment + "--" + subdomain

    updates = {
        'hostname': hostname,
    }

    if domain:
        updates['project_hostname'] = subdomain + "." + domain
        updates['full_hostname'] = hostname + "." + domain
        updates['ext_node_hostname'] = hostname + "--%s." + domain

    if intdomain:
        updates['int_project_hostname'] = subdomain + "." + intdomain
        updates['int_full_hostname'] = hostname + "." + intdomain
        updates['int_node_hostname'] = hostname + "--%s." + intdomain

    struct.update(updates)
    return struct

def build_context(pname, **more_context):
    """builds a dictionary called the `context` that is used when rendering the final cloudformation/terraform template.
    `more_context` is used to provide additional runtime data that can tweak the final dictionary.
    For example, we can specify an alternative AWS configuration or the context from a previous build."""

    supported_projects = project.project_list()
    ensure(pname in supported_projects, "Unknown project %r. Known projects: %s" % (pname, supported_projects))

    # this is the context data from the currently existing template (if any)
    # by re-using current values we can avoid making unnecessary changes when
    # regenerating templates (like random passwords)
    existing_context = more_context.pop('existing_context', {})

    # order is important. always use `alt-config` in `more_context` (explicit) when regenerating
    alt_config = more_context.get('alt-config')

    project_data = project.project_data(pname)
    if alt_config and project_data.get('aws-alt', {}).get(alt_config):
        project_data = project.set_project_alt(project_data, 'aws', alt_config)
    if alt_config and project_data.get('gcp-alt', {}).get(alt_config):
        project_data = project.set_project_alt(project_data, 'gcp', alt_config)
    if project_data.get('aws-alt'):
        del project_data['aws-alt']
    if project_data.get('gcp-alt'):
        del project_data['gcp-alt']

    defaults = {
        'project_name': pname,
        # 'project': project_data,

        'author': config.STACK_AUTHOR,

        # lsh@2022-02-16: disabled. dates make testing difficult and this value doesn't appear to be used.
        # 'date_rendered': utils.ymd(), # TODO: if this value is used at all, more precision might be nice

        # a stackname looks like: <pname>--<instance_id>[--<cluster-id>]
        'stackname': None, # must be provided by whatever is calling this
        'instance_id': None, # derived from the stackname
        'cluster_id': None, # derived from the stackname

        'alt-config': None,

        'branch': project_data.get('default-branch'),
        # used to checkout a specific revision of a project or a container.
        # value may be modified in-place on the created instance by Jenkins.
        'revision': None,

        # TODO: shift these rds_ values under the 'rds' key
        'rds_dbname': None, # generated from the instance_id when present
        'rds_username': None, # could possibly live in the project data, but really no need.
        'rds_password': None,
        'rds_instance_id': None,
        'rds': {},

        'ec2': False,
        's3': {},
        'eks': False,
        'elb': False,
        'alb': False,
        'sns': [],
        'sqs': {},
        'ext': False,
        'cloudfront': False,
        'elasticache': False,
        'docdb': False,
        'waf': False,
    }

    context = deepcopy(defaults)
    context.update(more_context)

    ensure('stackname' in context, "'stackname' not provided") # this still sucks

    # order is *not* important, one wrangler shouldn't depend on another
    wrangler_list = [
        partial(build_context_rds, existing_context=existing_context),
        build_context_aws,
        build_context_terraform,
        build_context_ec2,
        build_context_elb,
        build_context_alb,
        build_context_elb_alb,
        build_context_cloudfront,
        build_context_sns_sqs,
        build_context_s3,
        build_context_cloudfront,
        build_context_fastly,
        build_context_gcs,
        build_context_bigquery,
        build_context_eks,
        build_context_subdomains,
        build_context_elasticache,
        build_context_vault,
        partial(build_context_docdb, existing_context=existing_context),
        build_context_waf,
    ]

    # ... exceptions to the rule
    wrangler_list = [project_wrangler] + wrangler_list

    for wrangler in wrangler_list:
        # `deepcopy` here so functions can't modify the `context` in-place or
        # reference a bit of project_data and then change it
        context = wrangler(deepcopy(project_data), deepcopy(context))

    return context

#
# wranglers.
# these should accept the project data `pdata` and the `context` and
# then modify and return their local copy of the `context`.
#
# the `pdata` they receive has already had any alt-configs merged in.
#
# the final context is used to render CloudFormation and Terraform templates.
# the logic in `buildercore/cloudformation.py` and `buildercore/terraform.py` should *not*
# be creating default values or filling in blanks or doing any guessing at all.
# Do that here.
#

def build_context_waf(pdata, context):
    if not pdata['aws'].get('waf'):
        return context
    context['waf'] = pdata['aws']['waf']

    new_managed_rules = {}
    for managed_rule_key, managed_rule in context['waf']['managed-rules'].items():
        vendor, rule_name = managed_rule_key.split('/', 1) # "AWS/SomeFooRuleSet" => "AWS", "SomeFooRuleSet"
        managed_rule['vendor'] = vendor
        managed_rule['name'] = rule_name
        new_key_name = "%s-%s" % (vendor, rule_name)
        new_managed_rules[new_key_name] = managed_rule

        # 'included' exists purely to illustrate which rules are *not* excluded.
        delkey(managed_rule, 'included')

    context['waf']['managed-rules'] = new_managed_rules
    context['waf']['description'] = lookup(pdata, 'aws.description', 'a web application firewall')

    return context

def build_context_docdb(pdata, context, existing_context=None):
    "DocumentDB (docdb) configuration"
    if not pdata['aws'].get('docdb'):
        return context

    existing_context = existing_context.get('docdb', {})

    generated_password = utils.random_alphanumeric(length=64)
    current_master_password = existing_context.get('master-user-password')

    context['docdb'] = pdata['aws']['docdb']
    # non-configurable (for now) options
    context['docdb'].update({
        'minor-version-upgrades': True,
        'master-username': 'root',
        'master-user-password': current_master_password or generated_password,
        'storage-encrypted': False
    })
    return context

def build_context_terraform(pdata, context):
    """adds the commonly used Terraform fields to the context under `terraform`."""
    context['terraform'] = pdata['terraform']
    return context

def build_context_aws(pdata, context):
    """adds the commonly used AWS fields to the context under `aws`.
    these are fields that are common to many resources such as `account-id` and `availability-zone`."""
    if 'aws' not in pdata:
        return context
    keepers = [
        'region',
        'account-id',
        'vpc-id',

        'subnet-id',
        'subnet-cidr',
        'availability-zone',

        'redundant-subnet-id',
        'redundant-subnet-cidr',
        'redundant-availability-zone',

        'redundant-subnet-id-2',
        'redundant-subnet-cidr-2',
        'redundant-availability-zone-2',
    ]
    context['aws'] = subdict(pdata['aws'], keepers)
    return context

def build_context_s3(pdata, context):
    default_bucket_configuration = {
        'sqs-notifications': {},
        'deletion-policy': 'delete',
        'website-configuration': None,
        'cors': None,
        'public': False,
        'encryption': False,
    }
    if pdata['aws'].get('s3'):
        for bucket_template_name in pdata['aws']['s3']:
            configuration = pdata['aws']['s3'][bucket_template_name]
            bucket_name = parameterize(context)(bucket_template_name)
            max_bucket_name_length = 63
            msg = "bucket name %r from template %r is longer than 63 characters: %s" % \
              (bucket_name, bucket_template_name, len(bucket_name))
            ensure(len(bucket_name) <= max_bucket_name_length, msg)
            context['s3'][bucket_name] = default_bucket_configuration.copy()
            context['s3'][bucket_name].update(configuration if configuration else {})
    return context

def build_context_sns_sqs(pdata, context):
    _parameterize = parameterize(context)

    for topic_template_name in pdata['aws'].get('sns', []):
        topic_name = _parameterize(topic_template_name)
        context['sns'].append(topic_name)

    for queue_template_name in pdata['aws'].get('sqs', {}):
        queue_name = _parameterize(queue_template_name)
        queue_configuration = pdata['aws']['sqs'][queue_template_name]
        subscriptions = lmap(_parameterize, queue_configuration.get('subscriptions', []))
        context['sqs'][queue_name] = subscriptions
    return context

def project_wrangler(pdata, context):
    bits = core.parse_stackname(context['stackname'], all_bits=True, idx=True)
    pname = context['project_name']
    ensure(bits['project_name'] == pname,
           "the project name %r derived from the given `stackname` %r doesn't match" % (bits['project_name'], pname))
    # provides 'project_name', 'instance_id', 'cluster_id'
    context.update(bits)

    # hostname data
    # provides: 'domain', 'int_domain', 'subdomain',
    #           'hostname', 'project_hostname', 'int_project_hostname',
    #           'full_hostname', 'int_full_hostname'
    context.update(hostname_struct(context['stackname']))

    # project data
    # preseve some of the project data. all of it is too much
    keepers = [
        'salt',
        'formula-repo',
        'formula-dependencies',
    ]
    context['project'] = subdict(pdata, keepers)

    # limited to just master/masterless servers
    is_masterless = pdata['aws'].get('ec2') and pdata['aws']['ec2']['masterless']
    is_master = core.is_master_server_stack(context['stackname'])
    if is_master or is_masterless:
        keepers = [
            'private-repo',
            'configuration-repo',
        ]
        context['project'].update(subdict(pdata, keepers))

    return context

def set_master_address(pdata, context, master_ip=None):
    "can update both context and buildvars data"
    master_ip = master_ip or context['ec2'].get('master_ip')
    ensure(master_ip, "a master-ip was neither explicitly given nor found in the data provided")
    context['ec2']['master_ip'] = master_ip
    # lsh@2022-07-06: what is this 'aws' check for?
    if 'aws' in pdata and lookup(context, 'ec2.masterless', False):
        # this is a masterless instance, delete key
        del context['ec2']['master_ip']
    return context

def build_context_ec2(pdata, context):
    if 'ec2' not in pdata['aws']:
        return context

    stackname = context['stackname']

    # ec2
    # TODO: this is a problem. using the default 'True' preserves the behaviour of
    # when 'ec2: True' meant, 'use defaults with nothing changed'
    # but now I need to store master ip info there.

    # lsh@2021-06-22: `True` should not be valid for 'ec2'
    # I've replaced the alt-config '1804' with `ec2: {}` so config merging happens properly.
    # I suspect the project_data caching oversight was allowing this to pass.

    context['ec2'] = pdata['aws'].get('ec2')
    if context["ec2"] is True:
        msg = "'ec2: True' is no longer supported, stack needs it's context refreshed: %s" % stackname
        LOG.warning(msg)
        raise ValueError(msg)

    if context["ec2"] is False:
        return context

    # we can now assume this will always be a dict

    # lsh@2022-02-23: new failure cases for old configuration.
    if 'type' in pdata['aws']:
        msg = "'aws.type' is no longer supported, use 'aws.ec2.type': %s" % stackname
        LOG.warning(msg)
    if 'ports' in pdata['aws']:
        msg = "'aws.ports' is no longer supported, use 'aws.ec2.ports' instead: %s" % stackname
        LOG.warning(msg)

    context['ec2'] = pdata['aws']['ec2']
    context['ec2']['ports'] = pdata['aws']['ec2'].get('ports', {})

    set_master_address(pdata, context) # mutator

    if 'ext' in pdata['aws']:
        context['ext'] = pdata['aws']['ext']

    if 'root' in context['ec2']:
        if "type" not in context["ec2"]["root"]:
            context['ec2']['root']['type'] = 'gp2'
        if "device" not in context["ec2"]["root"]:
            context['ec2']['root']['device'] = '/dev/sda1'

    return context

def build_context_rds(pdata, context, existing_context):
    if 'rds' not in pdata['aws']:
        return context

    stackname = context['stackname']

    # used to give mysql a range of valid ip addresses to connect from
    subnet_cidr = netaddr.IPNetwork(pdata['aws']['subnet-cidr'])
    net = subnet_cidr.network
    mask = subnet_cidr.netmask
    networkmask = "%s/%s" % (net, mask) # "10.0.2.0/255.255.255.0"

    # pull password from existing context, if it exists
    generated_password = utils.random_alphanumeric(length=32)
    rds_password = existing_context.get('rds_password') or generated_password

    auto_rds_dbname = slugify(stackname, separator="") # lax--prod => laxprod
    existing_rds_dbname = existing_context.get('rds_dbname')
    override = lookup(pdata, 'aws.rds.db-name', None)
    rds_dbname = override or existing_rds_dbname or auto_rds_dbname

    updating = bool(existing_context)
    replacing = False

    context['rds'] = pdata['aws']['rds']

    if updating:
        # what conditions (supported by builder) will cause a db replacement?
        # - https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-rds-database-instance.html
        path_list = [('rds.snapshot-id', None),
                     ('rds.encryption', False),
                     ('rds.db-name', None)]
        for path, default in path_list:
            old_val = lookup(existing_context, path, default)
            new_val = lookup(context, path, default)
            if new_val != old_val:
                #print("%s old %r vs new %r" % (path, old_val, new_val))
                replacing = True

    num_replacements = 0
    if replacing:
        # has the db been replaced before? if so, we need to increment a number as
        # the Cloudformation generation (trop.py) doesn't have access to previously generated templates.
        # if the AttachedDB is to be replaced, it needs a new custom name.
        num_replacements = lookup(existing_context, 'rds.num-replacements', 0)
        num_replacements += 1

    rds_instance_id = core.rds_iid(stackname, num_replacements)

    context['rds'].update({
        'deletion-policy': lookup(pdata, 'aws.rds.deletion-policy', 'Snapshot'),
        'replacing': replacing,
        'num-replacements': num_replacements,
    })

    # don't introduce new 'db-name' field until we've migrated 'rds_dbname'
    if 'db-name' in context['rds']:
        del context['rds']['db-name']

    # TODO: shift the below under the 'rds' key
    context.update({
        'netmask': networkmask,
        'rds_username': 'root',
        'rds_password': rds_password,
        'rds_dbname': rds_dbname,
        'rds_instance_id': rds_instance_id,
        'rds_params': pdata['aws']['rds'].get('params', []),
    })

    return context

def build_context_elb(pdata, context):
    if 'elb' in pdata['aws']:
        context['elb'] = {}
        if isinstance(pdata['aws']['elb'], dict):
            context['elb'] = pdata['aws']['elb']
        context['elb'].update({
            'subnets': [
                pdata['aws']['subnet-id'],
                pdata['aws']['redundant-subnet-id'],
                pdata['aws']['redundant-subnet-id-2'],
            ],
        })
    return context

def build_context_alb(pdata, context):
    if 'alb' in pdata['aws'] and pdata['aws']['alb'] is not False:
        context['alb'] = pdata['aws']['alb']
        context['alb']['idle_timeout'] = str(context['alb']['idle_timeout'])
        context['alb']['subnets'] = [
            pdata['aws']['subnet-id'],
            pdata['aws']['redundant-subnet-id'],
            pdata['aws']['redundant-subnet-id-2'],
        ]
    return context

def build_context_elb_alb(pdata, context):
    "context for when both an ELBv1 and an ELBv2 (ALB) are present."
    if not ('alb' in pdata['aws'] and 'elb' in pdata['aws']):
        return context

    primary_lb = pdata['aws']['primary_lb']
    ensure(primary_lb in ['elb', 'alb'], "unknown value %r for 'primary_key'. expecting 'elb' or 'alb'." % primary_lb)

    context['primary_lb'] = primary_lb
    return context

def build_context_cloudfront(pdata, context):
    _parameterize = parameterize(context)

    def build_subdomain(x):
        # "{instance}--cdn", "elifesciences.org" => "foo--cdn.elifesciences.org"
        return complete_domain(_parameterize(x), context['domain'])

    context['cloudfront'] = False
    if 'cloudfront' in pdata['aws'] and pdata['aws']['cloudfront']:
        errors = None
        if pdata['aws']['cloudfront']['errors']:
            errors = {
                'domain': _parameterize(pdata['aws']['cloudfront']['errors']['domain']),
                'pattern': pdata['aws']['cloudfront']['errors']['pattern'],
                'codes': pdata['aws']['cloudfront']['errors']['codes'],
                'protocol': pdata['aws']['cloudfront']['errors']['protocol'],
            }
        context['cloudfront'] = {
            'subdomains': [build_subdomain(x) for x in pdata['aws']['cloudfront']['subdomains']],
            'subdomains-without-dns': [build_subdomain(x) for x in pdata['aws']['cloudfront']['subdomains-without-dns']],
            'cookies': pdata['aws']['cloudfront']['cookies'],
            'compress': pdata['aws']['cloudfront']['compress'],
            'headers': pdata['aws']['cloudfront']['headers'],
            'default-ttl': pdata['aws']['cloudfront']['default-ttl'],
            'errors': errors,
            'logging': pdata['aws']['cloudfront'].get('logging', False),
            'origins': OrderedDict([
                (o_id, {
                    'hostname': _parameterize(o['hostname']),
                    'pattern': o.get('pattern'),
                    'headers': o.get('headers', []),
                    'cookies': o.get('cookies', []),
                })
                for o_id, o in pdata['aws']['cloudfront']['origins'].items()
            ]),
        }
        iam_cert = pdata['aws']['cloudfront'].get('certificate_id', False)
        if iam_cert:
            context['cloudfront']['certificate_id'] = iam_cert

        acm_cert = pdata['aws']['cloudfront'].get('certificate', False)
        if acm_cert:
            context['cloudfront']['certificate'] = acm_cert

    return context

def build_context_fastly(pdata, context):
    _parameterize = parameterize(context)

    def _build_subdomain(x):
        return complete_domain(_parameterize(x), context['domain'])

    def _build_shield(shield):
        if shield is False:
            return {}

        if shield is True:
            pop = FASTLY_AWS_REGION_SHIELDS.get(pdata['aws']['region'], 'us-east-1')
            return {'pop': pop}

        return shield

    def _build_backend(backend):
        backend['hostname'] = _parameterize(backend['hostname'])
        backend['shield'] = _build_shield(backend.get('shield', pdata['aws']['fastly'].get('shield', False)))
        return backend

    def _parameterize_gcslogging(gcslogging):
        if gcslogging:
            gcslogging['bucket'] = _parameterize(gcslogging['bucket'])
            gcslogging['path'] = _parameterize(gcslogging['path'])

        return gcslogging

    def _parameterize_bigquerylogging(bigquerylogging):
        if bigquerylogging:
            bigquerylogging['dataset'] = _parameterize(bigquerylogging['dataset'])
            bigquerylogging['table'] = _parameterize(bigquerylogging['table'])

        return bigquerylogging

    context['fastly'] = False
    # as 'domain' is the top-level elifesciences.org used to build DNS entries, if it's not around it means
    # no DNS entries are possible and hence no Fastly CDN can be setup
    if pdata['domain'] and pdata['aws'].get('fastly'):
        backends = pdata['aws']['fastly'].get('backends', OrderedDict({}))
        context['fastly'] = {
            'backends': OrderedDict([(n, _build_backend(b)) for n, b in backends.items()]),
            'subdomains': [_build_subdomain(x) for x in pdata['aws']['fastly']['subdomains']],
            'subdomains-without-dns': [_build_subdomain(x) for x in pdata['aws']['fastly']['subdomains-without-dns']],
            'shield': _build_shield(pdata['aws']['fastly'].get('shield', False)),
            'dns': pdata['aws']['fastly']['dns'],
            'default-ttl': pdata['aws']['fastly']['default-ttl'],
            'healthcheck': pdata['aws']['fastly']['healthcheck'],
            'errors': pdata['aws']['fastly']['errors'],
            'gcslogging': _parameterize_gcslogging(pdata['aws']['fastly']['gcslogging']),
            'bigquerylogging': _parameterize_bigquerylogging(pdata['aws']['fastly']['bigquerylogging']),
            'ip-blacklist': pdata['aws']['fastly']['ip-blacklist'],
            'vcl-templates': pdata['aws']['fastly']['vcl-templates'],
            'vcl': pdata['aws']['fastly']['vcl'],
            'surrogate-keys': pdata['aws']['fastly']['surrogate-keys'],
        }
    return context

def build_context_gcs(pdata, context):
    context['gcs'] = False
    if 'gcs' in pdata['aws']:
        context['gcs'] = OrderedDict()
        for bucket_template_name, options in pdata['aws']['gcs'].items():
            bucket_name = parameterize(context)(bucket_template_name)
            context['gcs'][bucket_name] = {
                'project': options['project'],
            }
    return context

def build_context_bigquery(pdata, context):
    context['bigquery'] = False
    if pdata['gcp']['bigquery']:
        context['bigquery'] = OrderedDict()
        for dataset_template_name, options in pdata['gcp']['bigquery'].items():
            dataset_name = parameterize(context)(dataset_template_name)
            context['bigquery'][dataset_name] = {
                'project': options['project'],
                'tables': options.get('tables', OrderedDict()),
            }
    return context

def build_context_eks(pdata, context):
    if not pdata['aws'].get('eks'):
        return context

    context['eks'] = pdata['aws']['eks']

    def _build_addon_policy(label, data):
        return {
            'service-account': data.get('service-account'),
            'namespace': data.get('namespace'),
            'managed-policy': data.get('managed-policy', False),
            'policy-template': data.get('policy-template', False),
        }

    addons = {}
    for label, data in pdata['aws']['eks'].get('addons', {}).items():
        addons[label] = {
            'name': data.get('name', label), # name of the addon returned from DescribeAddonVersions API request, e.g. kube-proxy
            'label': data.get('label', label), # local label for terraform resource e.g. "kube_proxy"
            'version': data.get('version', 'latest'),
            'configuration-values': data.get('configuration-values', None),
            'resolve-conflicts-on-create': 'OVERWRITE',
            'resolve-conflicts-on-update': 'PRESERVE'
        }

        # Check if this addons needs additional permissions granting to a kubernetes service account via IRSA
        irsa_role = data.get('irsa-role')
        if irsa_role:
            addons[label]['irsa-role'] = _build_addon_policy(label, irsa_role)

    context['eks']['addons'] = addons
    return context

def complete_domain(host, default_main):
    """converts a partial domain name into a complete one.
    an empty `host` will return `default_main` (typically 'elifesciences.org')
    a simple `host` like 'foo' will be expanded to 'foo.elifesciences.org'
    a complete `host` like 'foo.elifesciences.org' will be returned as-is."""
    # "" means "elifesciences.org" (top-level). see 'journal--prod' configuration.
    is_main = host == ''
    if is_main:
        return default_main
    # for cases like 'e-lifejournal.com'. see 'redirects' project.
    is_complete = host.count(".") > 0
    if is_complete:
        return host
    # "foo--cdn" + "." + "elifesciences.org" => "foo--cdn.elifesciences.org"
    return host + '.' + default_main

def build_context_subdomains(pdata, context):
    # note! a distinction is being made between 'subdomain' and 'subdomains'
    context['subdomains'] = []
    if pdata['domain'] and 'subdomains' in pdata['aws']:
        for subdomain in pdata['aws']['subdomains']:
            context['subdomains'].append(complete_domain(subdomain, pdata['domain']))
    return context

def build_context_elasticache(pdata, context):
    if 'elasticache' in pdata['aws']:
        context['elasticache'] = pdata['aws']['elasticache']
    return context

def build_context_vault(pdata, context):
    context['vault'] = pdata['aws'].get('vault', {})
    return context


def more_validation(json_template_str):
    "local cloudformation template checks. complements the validation AWS does"
    try:
        data = json.loads(json_template_str)
        # case: when "DBInstanceIdentifier" == "lax--temp2"
        # The parameter Filter: db-instance-id is not a valid identifier. Identifiers must begin with a letter;
        # must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.
        dbid = lookup(data, 'Resources.AttachedDB.Properties.DBInstanceIdentifier', False)
        if dbid:
            ensure('--' not in dbid, "database instance identifier contains a double hyphen: %r" % dbid)

        # case: s3 bucket names must be between 3 and 63 chars
        # case: s3 bucket names must not contain uppercase characters
        # - https://docs.aws.amazon.com/AmazonS3/latest/dev/BucketRestrictions.html
        bucket_list = [val for val in data.Get('Resources').values() if val.get('Type') == 'AWS::S3::Bucket']
        for bucket in bucket_list:
            bucket_name = bucket['Properties']['BucketName']
            length = len(bucket_name)
            min_length = 3
            max_length = 63
            # occasionally true with particularly long alt-config names and instance ids
            ensure(length >= min_length and length <= max_length, "s3 bucket names must be between 3 and 63 characters: %s" % bucket_name)
            # this shouldn't ever be true but it's good to fail here than part way through a migration
            ensure(not any(char.isupper() for char in bucket_name), "s3 bucket name must not contain uppercase characters: %s" % bucket_name)

    except BaseException:
        LOG.exception("uncaught error attempting to validate cloudformation template")
        raise

def validate_template(template_json):
    return cloudformation.validate_template(template_json)

def validate_project(pname, **extra):
    """validates all of project's possible cloudformation templates.
    only called during testing"""
    LOG.info('validating %s', pname)
    template = quick_render(pname)
    pdata = project.project_data(pname)
    altconfig = None

    cloudformation.validate_template(template)
    more_validation(template)
    LOG.debug("local validation of cloudformation template passed")
    # validate all alternative configurations
    for altconfig in pdata.get('aws-alt', {}):
        LOG.info('validating %s, %s', pname, altconfig)
        extra = {
            'alt-config': altconfig
        }
        template = quick_render(pname, **extra)
        cloudformation.validate_template(template)
        LOG.debug("remote validation of cloudformation template passed")

#
# create new template
#

def quick_render(project_name, **more_context):
    """generates a Cloudformation template for given `project_name` with dummy values overriden by anything in `more_context`.
    lsh@2021-09: only called during testing so far."""
    # set a dummy instance id if one hasn't been set.
    more_context['stackname'] = more_context.get('stackname', core.mk_stackname(project_name, 'dummy'))
    context = build_context(project_name, **more_context)
    return cloudformation.render_template(context)

def generate_stack(pname, **more_context):
    """given a project name and any context overrides, generates a Cloudformation
    stack file, writes it to file and returns a pair of (context, stackfilename)"""
    context = build_context(pname, **more_context)
    cloudformation_template = cloudformation.render_template(context)
    terraform_template = terraform.render(context)
    stackname = context['stackname']

    context_handler.write_context(stackname, context)
    cloudformation_template_file = cloudformation.write_template(stackname, cloudformation_template)
    terraform_template_file = terraform.write_template(stackname, terraform_template)
    return context, cloudformation_template_file, terraform_template_file

#
# update existing template
#


UPDATABLE_TITLE_PATTERNS = [
    '^CloudFront.*',
    '^ElasticLoadBalancer.*',
    '^EC2Instance.*',
    '.*Bucket$',
    '.*BucketPolicy',
    '^StackSecurityGroup$',
    '^ELBSecurityGroup$',
    '^CnameDNS.+$',
    'FastlyDNS\\d+$',
    '^AttachedDB$',
    '^AttachedDBSubnet$',
    '^ExtraStorage.+$',
    '^MountPoint.+$',
    '^IntDNS.*$',
    '^ElastiCache.*$',
    '^AZ.+$',
    '^InstanceId.+$',
    '^PrivateIP.+$',
    '^DomainName$',
    '^IntDomainName$',
    '^RDSHost$',
    '^RDSPort$',
    '^DocumentDB.*$',
    '^WAF$',
    '^WAFAssociation.+$',
    '^WAFIPSet.+',

    '^ELBv2$',
    '^ELBv2Listener.*',
    '^ELBv2TargetGroup.*',

    # note: can't add ExtDNS as it changes dynamically when we start/stop instances and
    # should not be touched after creation.
    # '^ExtDNS$',
]

# patterns that should be updateable if a load balancer (ElasticLoadBalancer, ELBv2) is involved.
LB_UPDATABLE_TITLE_PATTERNS = [
    '^ExtDNS$',
]

EC2_NOT_UPDATABLE_PROPERTIES = ['ImageId', 'Tags', 'UserData']

REMOVABLE_TITLE_PATTERNS = [
    '^CloudFront.*',
    '^CnameDNS\\d+$',
    'FastlyDNS\\d+$',
    '^ExtDNS$',
    '^ExtDNS1$',
    '^ExtraStorage.+$',
    '^MountPoint.+$',
    '^.+Queue$',
    '^EC2Instance.+$',
    '^IntDNS.*$',
    '^ElastiCache.*$',
    '^.+Topic$',
    '^AttachedDB\\d*$',
    '^AttachedDBSubnet$',
    '^VPCSecurityGroup$',
    '^KeyName$',
    '^WAF$',
    '^WAFAssociation.+$',
    '^WAFIPSet.+',
]

# patterns that should be removable if a load balancer (ElasticLoadBalancer, ELBv2) is involved.
LB_REMOVABLE_TITLE_PATTERNS = [
    '^ElasticLoadBalancer$',
    '^ELBSecurityGroup$',
    '^ELBv2.*',
]

# CloudFormation is nicely chopped up into:
# * what to add
# * what to modify
# * what to remove
# TODO: remove (plus, edit, minus) delegating to self.cloudformation instead
class Delta(namedtuple('Delta', ['plus', 'edit', 'minus', 'cloudformation', 'terraform'])):
    @classmethod
    def from_cloudformation_and_terraform(cls, cloud_formation_delta, terraform_delta):
        return cls(
            cloud_formation_delta.plus,
            cloud_formation_delta.edit,
            cloud_formation_delta.minus,
            cloud_formation_delta,
            terraform_delta
        )

    @property
    def cloudformation_non_empty(self):
        return any([
            self.plus['Resources'],
            self.plus['Outputs'],
            self.edit['Resources'],
            self.edit['Outputs'],
            self.minus['Resources'],
            self.minus['Outputs'],
        ])
_empty_cloudformation_dictionary = {'Resources': {}, 'Outputs': {}}
Delta.__new__.__defaults__ = (_empty_cloudformation_dictionary, _empty_cloudformation_dictionary, _empty_cloudformation_dictionary, None, None)


def template_delta(context):
    """given an already existing template, regenerates it and produces a delta containing only the new resources.
    Some existing resources are treated as immutable and not put in the delta.
    Most resources that support non-destructive updates like CloudFront are instead included."""
    old_template = cloudformation.read_template(context['stackname'])
    template = json.loads(cloudformation.render_template(context))

    removeable_title_patterns = REMOVABLE_TITLE_PATTERNS[:]
    updateable_title_patterns = UPDATABLE_TITLE_PATTERNS[:]

    # when should we be able to modify load balancers?
    # this condition covers the case of migrating from an ELB to an ALB.
    # it doesn't cover downgrading, removing an LB altogether etc.
    if 'ElasticLoadBalancer' in old_template['Resources']:
        updateable_title_patterns.extend(LB_UPDATABLE_TITLE_PATTERNS)
        removeable_title_patterns.extend(LB_REMOVABLE_TITLE_PATTERNS)

    def _related_to_ec2(output):
        if 'Value' in output:
            if 'Ref' in output['Value']:
                return 'EC2Instance' in output['Value']['Ref']
            if 'Fn::GetAtt' in output['Value']:
                return 'EC2Instance' in output['Value']['Fn::GetAtt'][0]
        return False

    def _title_is_updatable(title):
        return len([p for p in updateable_title_patterns if re.match(p, title)]) > 0

    def _title_is_removable(title):
        return len([p for p in removeable_title_patterns if re.match(p, title)]) > 0

    # TODO: investigate if this is still necessary
    # start backward compatibility code
    # back for when 'EC2Instance' was the title rather than 'EC2Instance1'
    if 'EC2Instance' in old_template['Resources']:
        if 'ExtraStorage' in template['Resources']:
            template['Resources']['ExtraStorage']['Properties']['AvailabilityZone']['Fn::GetAtt'][0] = 'EC2Instance'
        if 'MountPoint' in template['Resources']:
            template['Resources']['MountPoint']['Properties']['InstanceId']['Ref'] = 'EC2Instance'
        if 'IntDNS' in template['Resources']:
            template['Resources']['IntDNS']['Properties']['ResourceRecords'][0]['Fn::GetAtt'][0] = 'EC2Instance'
        if 'ExtDNS' in template['Resources']:
            template['Resources']['ExtDNS']['Properties']['ResourceRecords'][0]['Fn::GetAtt'][0] = 'EC2Instance'
    # end backward compatibility code

    def _title_has_been_updated(title, section):
        if section in old_template:
            # title was there before with a deprecated name, leave it alone
            # e.g. 'EC2Instance' rather than 'EC2Instance1'
            if title not in old_template[section]:
                return False
        else:
            LOG.warning("section %r not present in old template but is present in new: %s", section, title)
            return False # can we handle this better?

        title_in_old = dict(old_template[section][title])
        title_in_new = dict(template[section][title])

        # ignore UserData changes, it's not useful to update them and cause
        # a needless reboot
        if title_in_old.get('Type') == 'AWS::EC2::Instance':
            for property_name in EC2_NOT_UPDATABLE_PROPERTIES:
                title_in_new['Properties'][property_name] = title_in_old['Properties'][property_name]

        return title_in_old != title_in_new

    def legacy_title(title):
        # some titles like EC2Instance1 were originally EC2Instance
        # however, no reason not to let EC2Instance2 be created?
        if title in ['EC2Instance1', 'ExtraStorage1', 'MountPoint1']:
            return title.strip('1')
        return None

    delta_plus_resources = {
        title: r for (title, r) in template['Resources'].items()
        if (title not in old_template['Resources']
            and (legacy_title(title) not in old_template['Resources'])
            and (title != 'EC2Instance'))
    }
    delta_plus_outputs = {
        title: o for (title, o) in template.get('Outputs', {}).items()
        if (title not in old_template.get('Outputs', {}) and _title_is_updatable(title))
    }
    delta_plus_parameters = {
        title: o for (title, o) in template.get('Parameters', {}).items()
        if (title not in old_template.get('Parameters', {}))
    }

    delta_edit_resources = {
        title: r for (title, r) in template['Resources'].items()
        if (_title_is_updatable(title) and _title_has_been_updated(title, 'Resources'))
    }
    delta_edit_outputs = {
        title: o for (title, o) in template.get('Outputs', {}).items()
        if (_title_is_updatable(title) and _title_has_been_updated(title, 'Outputs'))
    }

    delta_minus_resources = {r: v for r, v in old_template['Resources'].items() if r not in template['Resources'] and _title_is_removable(r)}
    delta_minus_outputs = {o: v for o, v in old_template.get('Outputs', {}).items() if o not in template.get('Outputs', {})}
    delta_minus_parameters = {p: v for p, v in old_template.get('Parameters', {}).items() if p not in template.get('Parameters', {})}

    return Delta.from_cloudformation_and_terraform(
        cloudformation.CloudFormationDelta(
            {
                'Resources': delta_plus_resources,
                'Outputs': delta_plus_outputs,
                'Parameters': delta_plus_parameters,
            },
            {
                'Resources': delta_edit_resources,
                'Outputs': delta_edit_outputs,
            },
            {
                'Resources': delta_minus_resources,
                'Outputs': delta_minus_outputs,
                'Parameters': delta_minus_parameters,
            }
        ),
        terraform.generate_delta(context)
    )

def _current_cloudformation_template(stackname):
    "retrieves a template from the CloudFormation API, using it as the source of truth"
    cfn = core.boto_conn(stackname, 'cloudformation', client=True)
    try:
        return cfn.get_template(StackName=stackname)['TemplateBody']
    except botocore.exceptions.ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ValidationError':
            # CloudFormation template is not used for this stackname
            return cloudformation.EMPTY_TEMPLATE
        raise

def download_cloudformation_template(stackname):
    cloudformation.write_template(stackname, json.dumps(_current_cloudformation_template(stackname)))

def regenerate_stack(stackname, **more_context):
    current_context = context_handler.load_context(stackname)
    download_cloudformation_template(stackname)
    (pname, instance_id) = core.parse_stackname(stackname)
    more_context['stackname'] = stackname

    # lsh@2019-09-27: usage of `instance_id` here is wrong. `instance_id` looks like "foobar" in "journal--foobar"
    # and is only correct when an alt-config matches. We typically have alt-configs for our common environments, like
    # ci, end2end, prod, continuumtest and has thus worked stably for a while now.
    # ad-hoc instances whose instance-id does not match an environment will have it's alt-config ignored.
    # the alt-config used during instance creation is found in `current_context` (but may not have always been the case).
    # in fact, kubernetes-aws--test requires this fallback and will until alt-config is included in its context
    # however this fallback doesn't work as alt-config is `None`
    #more_context['alt-config'] = current_context.get('alt-config', instance_id)
    # if you run into this problem:
    # 1. $ aws s3 cp s3://elife-builder/contexts/kubernetes-aws--test.json kubernetes-aws--test.json
    # 2. edit the `alt-config` key
    # 3. $ aws s3 cp kubernetes-aws--test.json s3://elife-builder/contexts/kubernetes-aws--test.json

    more_context['alt-config'] = current_context.get('alt-config', None)
    context = build_context(pname, existing_context=current_context, **more_context)
    delta = template_delta(context)
    return context, delta, current_context
