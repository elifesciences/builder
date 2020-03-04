# coding: utf8

"""
Marshalls a collection of project information together in to a dictionary called the `context`.

When an instance of a project is launched on AWS, we need to tweak things a bit
with no manual steps in some cases, or as few as possible in other cases.

Case 1: New, standardized environment
We launch journal--ci, a testing instance for the journal project within the `ci` environment.

Case 2: Ad-hoc instances
We launch journal--testsomething, a testing instance we will use to check something works as expected.

Case 3: Stack updates
We want to add an external volume to an EC2 instance to increase available space, so we partially update the CloudFormation template to create it.

"""
import logging
import os, json
import re
from collections import OrderedDict, namedtuple
from functools import partial
import botocore
import netaddr
from . import utils, cloudformation, terraform, core, project, context_handler
from .utils import ensure, lmap, deepcopy, subdict

LOG = logging.getLogger(__name__)

FASTLY_AWS_REGION_SHIELDS = {
    'us-east-1': 'dca-dc-us', # N. Virginia: Ashburn
    'us-east-2': 'mdw-il-us', # Ohio: Chicago
    'us-west-1': 'sjc-ca-us', # N. California: San Jose
    'us-west-2': 'sea-wa-us', # Oregon: Seattle
    'ap-northeast-1': 'tokyo-jp2', # Tokyo: Tokyo
    'ap-northeast-2': 'tokyo-jp2', # Seoul: Tokyo
    'ap-northeast-3': 'osaka-jp', # Osaka-Local: Osaka
    'ap-south-1': 'singapore-sg', # Mumbai: Singapore (change to Mumbai when available)
    'ap-southeast-1': 'singapore-sg', # Singapore: Singapore
    'ap-southeast-2': 'sydney-au', # Sydney : Sydney
    'ca-central-1': 'yyz-on-ca', # Canada (Central): Toronto
    'cn-north-1': 'hongkong-hk', # Beijing: Hong Kong
    'cn-northwest-1': 'hongkong-hk', # Ningxia: Hong Kong
    'eu-central-1': 'frankfurt-de', # Frankfurt: Frankfurt
    'eu-west-1': 'london_city-uk', # Ireland: London City
    'eu-west-2': 'london_city-uk', # London: London City
    'eu-west-3': 'cdg-par-fr', # Paris: Paris
    'sa-east-1': 'gru-br-sa', # São Paulo: São Paulo
}

def parameterize(context):
    def wrapper(string):
        return string.format(**{'instance': context['instance_id']})
    return wrapper

def shuffle(lst):
    import random
    lst = list(lst)
    random.shuffle(lst)
    return lst

def build_context(pname, **more_context):
    """wrangles parameters into a dictionary (context) that can be given to
    whatever renders the final template"""

    supported_projects = project.project_list()
    ensure(pname in supported_projects, "Unknown project %r. Known projects: %s" % (pname, supported_projects))

    # this is the context data from the currently existing template (if any)
    # by re-using current values we can avoid making unnecessary changes when
    # regenerating templates (like random passwords)
    existing_context = more_context.pop('existing_context', {})

    # order is important. always use the alt-config in more_context (explicit) also when regenerating
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
        #'project': project_data,

        'author': os.environ.get("LOGNAME") or 'unknown',
        'date_rendered': utils.ymd(), # TODO: if this value is used at all, more precision might be nice

        # a stackname looks like: <pname>--<instance_id>[--<cluster-id>]
        'stackname': None, # must be provided by whatever is calling this
        'instance_id': None, # derived from the stackname
        'cluster_id': None, # derived from the stackname

        'alt-config': None,

        'branch': project_data.get('default-branch'),
        'revision': None, # may be used in future to checkout a specific revision of project

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
        'sns': [],
        'sqs': {},
        'ext': False,
        'cloudfront': False,
        'elasticache': False,
        # future use: decide at context generation time how many infrastructure tools are we going to use for this stackname
        #'infrastructure': {
        #    'cloudformation': False,
        #    'terraform': False,
        #}
    }

    context = deepcopy(defaults)
    context.update(more_context)

    ensure('stackname' in context, "'stackname' not provided") # this still sucks

    # proceed with wrangling

    # why shuffle? so we don't have a context builder depending
    # on another context builder mutating the context in a specific way
    # wrangler_list = shuffle([
    wrangler_list = [
        partial(build_context_rds, existing_context=existing_context),
        build_context_aws,
        build_context_ec2,
        build_context_elb,
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
    ]

    # exceptions to the rule ...
    wrangler_list = [project_wrangler] + wrangler_list

    for wrangler in wrangler_list:
        # using `deepcopy` so functions can't modify the context in-place or
        # reference a bit of project_data and then change it
        context = wrangler(deepcopy(project_data), deepcopy(context))

    return context

def build_context_aws(pdata, context):
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
    ]
    context['aws'] = subdict(pdata['aws'], keepers)
    return context

def build_context_s3(pdata, context):
    # future: build what is necessary for buildercore.bootstrap.setup_s3()
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
    context.update(core.hostname_struct(context['stackname']))

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
    if 'aws' in pdata:
        if context['ec2'].get('masterless'):
            # this is a masterless instance, delete key
            del context['ec2']['master_ip']
    return context

def build_context_ec2(pdata, context):
    if 'ec2' not in pdata['aws']:
        return context
    # ec2
    # TODO: this is a problem. using the default 'True' preserves the behaviour of
    # when 'ec2: True' meant, 'use defaults with nothing changed'
    # but now I need to store master ip info there.
    context['ec2'] = pdata['aws'].get('ec2')
    if context['ec2'] == True:
        LOG.warn("stack needs it's context refreshed: %s", context['stackname'])

    elif context['ec2'] == False:
        return context

    # we can now assume this will always be a dict

    context['ec2'] = pdata['aws']['ec2']
    context['ec2']['type'] = pdata['aws']['type'] # TODO: shift aws.type to aws.ec2.type in project file
    context['ec2']['ports'] = pdata['aws'].get('ports', {}) # TODO: shift aws.ports to aws.ec2.ports in project file

    set_master_address(pdata, context) # mutator

    if 'ext' in pdata['aws']:
        context['ext'] = pdata['aws']['ext']

    return context

def build_context_rds(pdata, context, existing_context):
    if 'rds' not in pdata['aws']:
        return context
    stackname = context['stackname']

    # deletion policy
    deletion_policy = utils.lookup(pdata, 'aws.rds.deletion-policy', 'Snapshot')

    # used to give mysql a range of valid ip addresses to connect from
    subnet_cidr = netaddr.IPNetwork(pdata['aws']['subnet-cidr'])
    net = subnet_cidr.network
    mask = subnet_cidr.netmask
    networkmask = "%s/%s" % (net, mask) # ll: 10.0.2.0/255.255.255.0

    # pull password from existing context, if it exists
    generated_password = utils.random_alphanumeric(length=32)
    rds_password = existing_context.get('rds_password')
    if not rds_password:
        # may be present but None
        rds_password = generated_password

    # TODO: shift the below under a 'rds' key
    context.update({
        'netmask': networkmask,
        'rds_username': 'root',
        'rds_password': rds_password,
        # alpha-numeric only
        'rds_dbname': core.rds_dbname(stackname, context), # name of default application db
        'rds_instance_id': core.rds_iid(stackname), # name of rds instance
        'rds_params': pdata['aws']['rds'].get('params', []),
        'rds': pdata['aws']['rds'],
    })
    context['rds']['deletion-policy'] = deletion_policy

    return context

def build_context_elb(pdata, context):
    if 'elb' in pdata['aws']:
        context['elb'] = {}
        if isinstance(pdata['aws']['elb'], dict):
            context['elb'] = pdata['aws']['elb']
        context['elb'].update({
            'subnets': [
                pdata['aws']['subnet-id'],
                pdata['aws']['redundant-subnet-id']
            ],
        })
    return context

def build_context_cloudfront(pdata, context):
    _parameterize = parameterize(context)

    def build_subdomain(x):
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
            'certificate_id': pdata['aws']['cloudfront']['certificate_id'],
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
    if pdata['aws'].get('eks'):
        context['eks'] = pdata['aws']['eks']

    return context

def complete_domain(host, default_main):
    is_main = host == ''
    is_complete = host.count(".") > 0
    if is_main:
        return default_main
    elif is_complete:
        return host
    return host + '.' + default_main # something + '.' + elifesciences.org

def build_context_subdomains(pdata, context):
    # note! a distinction is being made between 'subdomain' and 'subdomains'
    context['subdomains'] = [complete_domain(s, pdata['domain']) for s in pdata['aws'].get('subdomains', []) if pdata['domain']]
    return context

def build_context_elasticache(pdata, context):
    if 'elasticache' in pdata['aws']:
        context['elasticache'] = pdata['aws']['elasticache']
    return context

def build_context_vault(pdata, context):
    context['vault'] = pdata['aws'].get('vault', {})
    return context

#
#
#

def more_validation(json_template_str):
    "local cloudformation template checks. complements the validation AWS does"
    try:
        data = json.loads(json_template_str)
        # case: when "DBInstanceIdentifier" == "lax--temp2"
        # The parameter Filter: db-instance-id is not a valid identifier. Identifiers must begin with a letter;
        # must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.
        dbid = utils.lookup(data, 'Resources.AttachedDB.Properties.DBInstanceIdentifier', False)
        if dbid:
            ensure('--' not in dbid, "database instance identifier contains a double hyphen: %r" % dbid)

        # case: s3 bucket names must be between 3 and 63 chars
        # case: s3 bucket names must not contain uppercase characters
        # - https://docs.aws.amazon.com/AmazonS3/latest/dev/BucketRestrictions.html
        bucket_map = utils.dictfilter(lambda key, val: val.get('Type') == "AWS::S3::Bucket", data.get('Resources'))
        for bucket_map in bucket_map.values():
            bucket_name = bucket_map['Properties']['BucketName']
            length = len(bucket_name)
            # occasionally true with particularly long alt-config names and instance ids
            ensure(length >= 3 and length <= 63, "s3 bucket names must be between 3 and 63 characters: %s" % bucket_name)
            # this shouldn't ever be true but it's good to fail here than part way through a migration
            ensure(not any(char.isupper() for char in bucket_name), "s3 bucket name must not contain uppercase characters: %s" % bucket_name)

        return True
    except BaseException:
        LOG.exception("uncaught error attempting to validate cloudformation template")
        raise

def validate_project(pname, **extra):
    """validates all of project's possible cloudformation templates.
    only called during testing"""
    LOG.info('validating %s', pname)
    template = quick_render(pname)
    pdata = project.project_data(pname)
    altconfig = None

    cloudformation.validate_template(pname, template)
    more_validation(template)
    LOG.debug("local validation of cloudformation template passed")
    # validate all alternative configurations
    for altconfig in pdata.get('aws-alt', {}).keys():
        LOG.info('validating %s, %s', pname, altconfig)
        extra = {
            'alt-config': altconfig
        }
        template = quick_render(pname, **extra)
        cloudformation.validate_template(pname, template)
        LOG.debug("remote validation of cloudformation template passed")

#
# create new template
#

def quick_render(project_name, **more_context):
    """generates a representative Cloudformation template for given project with dummy values
    only called during testing"""
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


# can't add ExtDNS: it changes dynamically when we start/stop instances and should not be touched after creation
UPDATABLE_TITLE_PATTERNS = ['^CloudFront.*', '^ElasticLoadBalancer.*', '^EC2Instance.*', '.*Bucket$', '.*BucketPolicy', '^StackSecurityGroup$', '^ELBSecurityGroup$', '^CnameDNS.+$', 'FastlyDNS\\d+$', '^AttachedDB$', '^AttachedDBSubnet$', '^ExtraStorage.+$', '^MountPoint.+$', '^IntDNS.*$', '^ElastiCache.*$', '^AZ.+$', '^InstanceId.+$', '^PrivateIP.+$', '^DomainName$', '^IntDomainName$', '^RDSHost$', '^RDSPort$']

REMOVABLE_TITLE_PATTERNS = ['^CloudFront.*', '^CnameDNS\\d+$', 'FastlyDNS\\d+$', '^ExtDNS$', '^ExtDNS1$', '^ExtraStorage.+$', '^MountPoint.+$', '^.+Queue$', '^EC2Instance.+$', '^IntDNS.*$', '^ElastiCache.*$', '^.+Topic$', '^AttachedDB$', '^AttachedDBSubnet$', '^VPCSecurityGroup$', '^KeyName$']
EC2_NOT_UPDATABLE_PROPERTIES = ['ImageId', 'Tags', 'UserData']

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

    Some the existing resources are treated as immutable and not put in the delta. Most that support non-destructive updates like CloudFront are instead included"""
    old_template = cloudformation.read_template(context['stackname'])
    template = json.loads(cloudformation.render_template(context))

    def _related_to_ec2(output):
        if 'Value' in output:
            if 'Ref' in output['Value']:
                return 'EC2Instance' in output['Value']['Ref']
            if 'Fn::GetAtt' in output['Value']:
                return 'EC2Instance' in output['Value']['Fn::GetAtt'][0]
        return False

    def _title_is_updatable(title):
        return len([p for p in UPDATABLE_TITLE_PATTERNS if re.match(p, title)]) > 0

    def _title_is_removable(title):
        return len([p for p in REMOVABLE_TITLE_PATTERNS if re.match(p, title)]) > 0

    # TODO: investigate if this is still necessary
    # start backward compatibility code
    # back for when EC2Instance was the title rather than EC2Instance1
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
            if not title in old_template[section]:
                return False
        else:
            LOG.warn("section %r not present in old template but is present in new: %s" % (section, title))
            return False # can we handle this better?

        title_in_old = dict(old_template[section][title])
        title_in_new = dict(template[section][title])
        # ignore UserData changes, it's not useful to update them and cause
        # a needless reboot
        if 'Type' in title_in_old:
            if title_in_old['Type'] == 'AWS::EC2::Instance':
                for property_name in EC2_NOT_UPDATABLE_PROPERTIES:
                    title_in_new['Properties'][property_name] = title_in_old['Properties'][property_name]
        return title_in_old != title_in_new

    def legacy_title(title):
        # some titles like EC2Instance1 were originally EC2Instance
        # however, no reason not to let EC2Instance2 be created?
        if title in ['EC2Instance1', 'ExtraStorage1', 'MountPoint1']:
            return title.strip('1')

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
    more_context['stackname'] = stackname # TODO: purge this crap
    # lsh@2019-09-27: usage of `instance_id` here is wrong. `instance_id` looks like "foobar" in "journal--foobar"
    # and is only correct when an alt-config matches. We typically have alt-configs for our common environments, like
    # ci, end2end, prod, continuumtest and has thus worked stably for a while now.
    # ad-hoc instances whose instance-id does not match an environment will have it's alt-config ignored.
    # the alt-config used during instance creation is found in `current_context` (but may not have always been the case).
    #more_context['alt-config'] = instance_id
    #more_context['alt-config'] = current_context.get('alt-config', instance_id)
    more_context['alt-config'] = current_context['alt-config']
    context = build_context(pname, existing_context=current_context, **more_context)
    delta = template_delta(context)
    return context, delta, current_context
