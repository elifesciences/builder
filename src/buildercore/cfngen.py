"""
Generates AWS CloudFormation (cfn) templates.

Marshalls a collection of project information together in the `build_context()`
function, then passes this Troposphere in `trop.py` to generate the final cfn
template.

When an instance of a project is launched on AWS, we need to tweak things a bit
with no manual steps in some cases, or as few as possible in other cases.

Case 1: New, standardized environment
We launch journal--ci, a testing instance for the journal project within the `ci` environment.

Case 2: Ad-hoc instances
We launch journal--testsomething, a testing instance we will use to check something works as expected.

Case 3: Stack updates
We want to add an external volume to an EC2 instance to increase available space, so we partially update the CloudFormation template to create it.

"""
import os, json, copy
import re
from collections import OrderedDict, namedtuple
import netaddr
from slugify import slugify
from . import utils, trop, core, project, context_handler
from .utils import ensure, lmap
from .config import STACK_DIR

import logging

LOG = logging.getLogger(__name__)

# TODO: this function needs some TLC - it's getting fat.
def build_context(pname, **more_context): # pylint: disable=too-many-locals
    """wrangles parameters into a dictionary (context) that can be given to
    whatever renders the final template"""

    supported_projects = project.project_list()
    ensure(pname in supported_projects, "Unknown project %r. Known projects: %s" % (pname, supported_projects))

    # this is the context data from the currently existing template (if any)
    # by re-using current values we can avoid making unnecessary changes when
    # regenerating templates (like random passwords)
    existing_context = more_context.pop('existing_context', {})

    # order is important. prefer the alt-config in more_context (explicit) over
    # any existing context (implicit)
    alt_config = utils.firstnn([
        more_context.get('alt-config'),
        existing_context.get('alt-config')
    ])

    project_data = project.project_data(pname)
    if alt_config:
        project_data = project.set_project_alt(project_data, 'aws', alt_config)
        more_context['alt-config'] = alt_config

    defaults = {
        'project_name': pname,
        'project': project_data,

        'author': os.environ.get("LOGNAME") or os.getlogin(),
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
        'elb': False,
        'sns': [],
        'sqs': {},
        'ext': False,
        'cloudfront': False,
        'elasticache': False,
    }

    context = copy.deepcopy(defaults)
    context.update(more_context)

    # proceed with wrangling

    # TODO: don't like this. if a stackname is required, make it a parameter.
    # stackname used to be derived inside this func from pname + id + cluster number
    ensure(context['stackname'], "a stackname wasn't provided.")
    stackname = context['stackname']

    # stackname data
    bits = core.parse_stackname(stackname, all_bits=True, idx=True)
    ensure(bits['project_name'] == pname,
           "the project name %r derived from the given `stackname` %r doesn't match" % (bits['project_name'], pname))
    context.update(bits)

    # hostname data
    context.update(core.hostname_struct(stackname))

    # rds
    context.update(build_context_rds(context, existing_context))

    if 'ext' in context['project']['aws']:
        context['ext'] = context['project']['aws']['ext']

    context['ec2'] = context['project']['aws'].get('ec2', True)
    if isinstance(context['ec2'], dict):
        context['ec2']['type'] = context['project']['aws']['type']

    build_context_elb(context)

    def _parameterize(string):
        return string.format(instance=context['instance_id'])

    for topic_template_name in context['project']['aws']['sns']:
        topic_name = _parameterize(topic_template_name)
        context['sns'].append(topic_name)

    for queue_template_name in context['project']['aws']['sqs']:
        queue_name = _parameterize(queue_template_name)
        queue_configuration = context['project']['aws']['sqs'][queue_template_name]
        subscriptions = lmap(_parameterize, queue_configuration.get('subscriptions', []))
        context['sqs'][queue_name] = subscriptions

    # future: build what is necessary for buildercore.bootstrap.setup_s3()
    default_bucket_configuration = {
        'sqs-notifications': {},
        'deletion-policy': 'delete',
        'website-configuration': None,
        'cors': None,
        'public': False,
    }
    for bucket_template_name in context['project']['aws']['s3']:
        bucket_name = _parameterize(bucket_template_name)
        configuration = context['project']['aws']['s3'][bucket_template_name]
        context['s3'][bucket_name] = default_bucket_configuration.copy()
        context['s3'][bucket_name].update(configuration if configuration else {})

    build_context_cloudfront(context, parameterize=_parameterize)
    build_context_subdomains(context)
    build_context_elasticache(context)

    return context


def build_context_rds(context, existing_context):
    if 'rds' not in context['project']['aws']:
        return {}
    stackname = context['stackname']

    # deletion policy
    deletion_policy = utils.lookup(context, 'project.aws.rds.deletion-policy', 'Snapshot')

    # used to give mysql a range of valid ip addresses to connect from
    subnet_cidr = netaddr.IPNetwork(context['project']['aws']['subnet-cidr'])
    net = subnet_cidr.network
    mask = subnet_cidr.netmask
    networkmask = "%s/%s" % (net, mask) # ll: 10.0.2.0/255.255.255.0

    # pull password from existing context, if it exists
    generated_password = utils.random_alphanumeric(length=32)
    rds_password = existing_context.get('rds_password', generated_password)

    return {
        'netmask': networkmask,
        'rds_username': 'root',
        'rds_password': rds_password,
        # alpha-numeric only
        # TODO: investigate possibility of ambiguous RDS naming here
        'rds_dbname': context.get('rds_dbname') or slugify(stackname, separator=""), # *must* use 'or' here
        'rds_instance_id': slugify(stackname), # *completely* different to database name
        'rds_params': context['project']['aws']['rds'].get('params', []),

        'rds': {
            'deletion-policy': deletion_policy
        }
    }


def build_context_elb(context):
    if 'elb' in context['project']['aws']:
        if isinstance(context['project']['aws']['elb'], dict):
            context['elb'] = context['project']['aws']['elb']
        else:
            context['elb'] = {}
        context['elb'].update({
            'subnets': [
                context['project']['aws']['subnet-id'],
                context['project']['aws']['redundant-subnet-id']
            ],
        })

def build_context_cloudfront(context, parameterize):
    def build_subdomain(x):
        return complete_domain(parameterize(x), context['domain'])
    if 'cloudfront' in context['project']['aws']:
        errors = None
        if context['project']['aws']['cloudfront']['errors']:
            errors = {
                'domain': parameterize(context['project']['aws']['cloudfront']['errors']['domain']),
                'pattern': context['project']['aws']['cloudfront']['errors']['pattern'],
                'codes': context['project']['aws']['cloudfront']['errors']['codes'],
                'protocol': context['project']['aws']['cloudfront']['errors']['protocol'],
            }
        context['cloudfront'] = {
            'subdomains': [build_subdomain(x) for x in context['project']['aws']['cloudfront']['subdomains']],
            'subdomains-without-dns': [build_subdomain(x) for x in context['project']['aws']['cloudfront']['subdomains-without-dns']],
            'certificate_id': context['project']['aws']['cloudfront']['certificate_id'],
            'cookies': context['project']['aws']['cloudfront']['cookies'],
            'compress': context['project']['aws']['cloudfront']['compress'],
            'headers': context['project']['aws']['cloudfront']['headers'],
            'default-ttl': context['project']['aws']['cloudfront']['default-ttl'],
            'errors': errors,
            'logging': context['project']['aws']['cloudfront'].get('logging', False),
            'origins': OrderedDict([
                (o_id, {
                    'hostname': parameterize(o['hostname']),
                    'pattern': o.get('pattern'),
                    'headers': o.get('headers', []),
                    'cookies': o.get('cookies', []),
                })
                for o_id, o in context['project']['aws']['cloudfront']['origins'].items()
            ]),
        }
    else:
        context['cloudfront'] = False

def complete_domain(host, default_main):
    is_main = host == ''
    is_complete = host.count(".") > 0
    if is_main:
        return default_main
    elif is_complete:
        return host
    return host + '.' + default_main # something + '.' + elifesciences.org

def build_context_subdomains(context):
    context['subdomains'] = [complete_domain(s, context['project']['domain']) for s in context['project']['aws'].get('subdomains', [])]

def build_context_elasticache(context):
    if 'elasticache' in context['project']['aws']:
        context['elasticache'] = context['project']['aws']['elasticache']

def choose_alt_config(stackname):
    """returns the name of the alt-config you think the user would want, based on given stackname"""
    pname, instance_id = core.parse_stackname(stackname)
    pdata = project.project_data(pname)
    if instance_id in project.project_alt_config_names(pdata):
        # instance_id exactly matches an alternative config. use that.
        return instance_id

#
#
#

def render_template(context, template_type='aws'):
    pname = context['project_name']
    msg = "could not render an %r template for %r: no %r context found" % (template_type, pname, template_type)
    ensure(template_type in context['project'], msg, ValueError)
    if template_type == 'aws':
        return trop.render(context)
    # are we saving this space for different template types in future?

def write_template(stackname, contents):
    "writes a json version of the python cloudformation template to the stacks directory"
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    open(output_fname, 'w').write(contents)
    return output_fname

def read_template(stackname):
    "returns the contents of a cloudformation template as a python data structure"
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    return json.load(open(output_fname, 'r'))

def validate_aws_template(pname, rendered_template):
    "remote cloudformation template checks."
    conn = core.connect_aws_with_pname(pname, 'cfn')
    return conn.validate_template(rendered_template)

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

        return True
    except BaseException:
        LOG.exception("uncaught error attempting to validate cloudformation template")
        raise

# TODO: shift this into testing and make each validation call a subTest
def validate_project(pname, **extra):
    """validates all of project's possible cloudformation templates.
    only called during testing"""
    import time, boto
    LOG.info('validating %s', pname)
    template = quick_render(pname)
    pdata = project.project_data(pname)
    altconfig = None
    try:
        validate_aws_template(pname, template)
        more_validation(template)
        # validate all alternative configurations
        for altconfig in pdata.get('aws-alt', {}).keys():
            LOG.info('validating %s, %s', pname, altconfig)
            extra = {
                'alt-config': altconfig
            }
            template = quick_render(pname, **extra)
            validate_aws_template(pname, template)
            time.sleep(0.5) # be nice, avoid any rate limiting

    except boto.connection.BotoServerError:
        msg = "failed:\n" + template + "\n%s (%s) template failed validation" % (pname, altconfig if altconfig else 'normal')
        LOG.exception(msg)
        return False

    return True

#
# create new template
#

def quick_render(project_name, **more_context):
    """generates a representative Cloudformation template for given project with dummy values
    only called during testing"""
    # set a dummy instance id if one hasn't been set.
    more_context['stackname'] = more_context.get('stackname', core.mk_stackname(project_name, 'dummy'))
    context = build_context(project_name, **more_context)
    return render_template(context)

def generate_stack(pname, **more_context):
    """given a project name and any context overrides, generates a Cloudformation
    stack file, writes it to file and returns a pair of (context, stackfilename)"""
    context = build_context(pname, **more_context)
    template = render_template(context)
    stackname = context['stackname']
    out_fname = write_template(stackname, template)
    context_handler.write_context(stackname, context)
    return context, out_fname

#
# update existing template
#


# can't add ExtDNS: it changes dynamically when we start/stop instances and should not be touched after creation
UPDATABLE_TITLE_PATTERNS = ['^CloudFront.*', '^ElasticLoadBalancer.*', '^EC2Instance.*', '.*Bucket$', '.*BucketPolicy', '^StackSecurityGroup$', '^ELBSecurityGroup$', '^CnameDNS.+$', '^AttachedDB$', '^AttachedDBSubnet$', '^ExtraStorage.+$', '^MountPoint.+$', '^IntDNS.*$', '^ElastiCache.*$']

REMOVABLE_TITLE_PATTERNS = ['^CnameDNS\\d+$', '^ExtDNS$', '^ExtraStorage.+$', '^MountPoint.+$', '^.+Queue$', '^EC2Instance.+$', '^IntDNS.*$', '^ElastiCache.*$', '^.+Topic$']
EC2_NOT_UPDATABLE_PROPERTIES = ['ImageId', 'Tags', 'UserData']

class Delta(namedtuple('Delta', ['plus', 'edit', 'minus'])):
    @property
    def non_empty(self):
        return self.plus['Resources'] or self.plus['Outputs'] or self.edit['Resources'] or self.edit['Outputs'] or self.minus['Resources'] or self.minus['Outputs']

def template_delta(context):
    """given an already existing template, regenerates it and produces a delta containing only the new resources.

    Some the existing resources are treated as immutable and not put in the delta. Most that support non-destructive updates like CloudFront are instead included"""
    old_template = read_template(context['stackname'])
    template = json.loads(render_template(context))

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
        # title was there before with a deprecated name, leave it alone
        # e.g. 'EC2Instance' rather than 'EC2Instance1'
        if not title in old_template[section]:
            return False

        title_in_old = dict(old_template[section][title])
        title_in_new = dict(template[section][title])
        # ignore UserData changes, it's not useful to update them and cause
        # a needless reboot
        if 'Type' in title_in_old:
            if title_in_old['Type'] == 'AWS::EC2::Instance':
                for property_name in EC2_NOT_UPDATABLE_PROPERTIES:
                    title_in_old['Properties'][property_name] = None
                    title_in_new['Properties'][property_name] = None
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
        if (title not in old_template.get('Outputs', {}) and not _related_to_ec2(o))
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

    return Delta(
        {
            'Resources': delta_plus_resources,
            'Outputs': delta_plus_outputs,
        },
        {
            'Resources': delta_edit_resources,
            'Outputs': delta_edit_outputs,
        },
        {
            'Resources': delta_minus_resources,
            'Outputs': delta_minus_outputs,
        }
    )

def merge_delta(stackname, delta):
    """Merges the new resources in delta in the local copy of the Cloudformation  template"""
    template = read_template(stackname)
    apply_delta(template, delta)
    write_template(stackname, json.dumps(template))
    return template

def apply_delta(template, delta):
    for component in delta.plus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.plus[component])
        template[component] = data
    for component in delta.edit:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.edit[component])
        template[component] = data
    for component in delta.minus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        for title in delta.minus[component]:
            del template[component][title]

# def regenerate_stack_vars(stackname, **more_context):
#    """returns the current template context and the new context for the given stackname.
#    use `cfngen.template_delta` to generate a list of changes"""
#    # fetch context used to build current stack
#    current_context = context_handler.load_context(stackname)
#    # don't rely on 'alt-config' being present in the current context, or if it is present,
#    # don't assume that alt-config existed when the current context existed. for example:
#    # `prod` used a local db before, same as default, but now a `prod` alt-config gets RDS
#    more_context['alt-config'] = choose_alt_config(stackname)
#    # build the context again, but this time re-use some current values/config
#    more_context['stackname'] = stackname # TODO: purge this crap
#    pname = core.parse_stackname(stackname)[0]
#    return current_context, build_context(pname, existing_context=current_context, **more_context)

def regenerate_stack(stackname, current_template, **more_context):
   # what is the point of these two lines? it downloads the template body and saves it to disk and never uses it ...
   # It's using the local disk as a cache for the template, rather than calling the API whenever is needed
   # if it was doing something important, it should be it's own function, like `write_cfn_template_to_disk` or whatever
   # as it is, it requires a dependency between cfngen and bootstrap (removed) that shouldn't really exist
    current_context = context_handler.load_context(stackname)
    write_template(stackname, json.dumps(current_template))
    pname = core.project_name_from_stackname(stackname)
    more_context['stackname'] = stackname # TODO: purge this crap
    context = build_context(pname, existing_context=current_context, **more_context)
    delta = template_delta(context)
    return context, delta, current_context
