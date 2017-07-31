"""
Generates AWS CloudFormation (cfn) templates.

Marshalls a collection of project information together in the `build_context()`
function, then passes this Troposphere in `trop.py` to generate the final cfn
template.

When an instance of a project is launched on AWS, we need to tweak things a bit
with no manual steps in some cases, or as few as possible in other cases.

Case 1: Continuous Deployment
After a successful build and test on the CI server, we want to deploy an instance.

Case 2: Ad-hoc instances
A developer wants a temporary instance deployed for testing or debugging.

"""
import os, json, copy
import re
from collections import OrderedDict
import netaddr
from slugify import slugify
from . import utils, trop, core, project, bootstrap, context_handler
from .utils import ensure
from .config import STACK_DIR

import logging

LOG = logging.getLogger(__name__)

# TODO: this function needs some TLC - it's getting fat.
def build_context(pname, **more_context): # pylint: disable=too-many-locals
    """wrangles parameters into a dictionary (context) that can be given to
    whatever renders the final template"""

    supported_projects = project.project_list()
    assert pname in supported_projects, "Unknown project %r" % pname

    project_data = project.project_data(pname)

    if 'alt-config' in more_context:
        project_data = project.set_project_alt(project_data, 'aws', more_context['alt-config'])

    defaults = {
        'project_name': pname,
        'project': project_data,

        'author': os.environ.get("LOGNAME") or os.getlogin(),
        'date_rendered': utils.ymd(),

        # a stackname looks like: <pname>--<instance_id>[--<cluster-id>]
        'stackname': None, # must be provided by whatever is calling this
        'instance_id': None, # derived from the stackname
        'cluster_id': None, # derived from the stackname

        'branch': project_data.get('default-branch'),
        'revision': None, # may be used in future to checkout a specific revision of project
        'rds_dbname': None, # generated from the instance_id when present
        'rds_username': None, # could possibly live in the project data, but really no need.
        'rds_password': None,
        'rds_instance_id': None,
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

    assert context['stackname'] is not None, "a stackname wasn't provided."
    stackname = context['stackname']

    # stackname data
    bit_keys = ['project_name', 'instance_id', 'cluster_id']
    bits = dict(zip(bit_keys, core.parse_stackname(stackname, all_bits=True)))
    assert bits['project_name'] == pname, \
        "the project name derived from the `stackname` doesn't match the given project name"
    context.update(bits)

    # hostname data
    context.update(core.hostname_struct(stackname))

    # post-processing
    if 'rds' in context['project']['aws']:
        default_rds_dbname = slugify(stackname, separator="")

        # used to give mysql a range of valid ip addresses to connect from
        subnet_cidr = netaddr.IPNetwork(context['project']['aws']['subnet-cidr'])
        net = subnet_cidr.network
        mask = subnet_cidr.netmask
        networkmask = "%s/%s" % (net, mask) # ll: 10.0.2.0/255.255.255.0

        # alpha-numeric only
        # TODO: investigate possibility of ambiguous RDS naming here
        context.update({
            'netmask': networkmask,
            'rds_username': 'root',
            'rds_password': utils.random_alphanumeric(length=32), # will be saved to build-vars.json
            'rds_dbname': context.get('rds_dbname') or default_rds_dbname, # *must* use 'or' here
            'rds_instance_id': slugify(stackname), # *completely* different to database name
            'rds_params': context['project']['aws']['rds'].get('params', [])
        })

    if 'ext' in context['project']['aws']:
        context['ext'] = context['project']['aws']['ext']

    # is this a production instance? if yes, then we'll do things like tweak the dns records ...
    context.update({
        'is_prod_instance': core.is_prod_stack(stackname),
    })

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
        subscriptions = []
        if 'subscriptions' in queue_configuration:
            for topic_template_name in queue_configuration['subscriptions']:
                subscriptions.append(_parameterize(topic_template_name))
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
        if context['project']['aws']['cloudfront']['errors']:
            errors = {
                'domain': parameterize(context['project']['aws']['cloudfront']['errors']['domain']),
                'pattern': context['project']['aws']['cloudfront']['errors']['pattern'],
                'codes': context['project']['aws']['cloudfront']['errors']['codes'],
                'protocol': context['project']['aws']['cloudfront']['errors']['protocol'],
            }
        else:
            errors = None
        context['cloudfront'] = {
            'subdomains': [build_subdomain(x) for x in context['project']['aws']['cloudfront']['subdomains']],
            'subdomains-without-dns': [build_subdomain(x) for x in context['project']['aws']['cloudfront']['subdomains-without-dns']],
            'certificate_id': context['project']['aws']['cloudfront']['certificate_id'],
            'cookies': context['project']['aws']['cloudfront']['cookies'],
            'compress': context['project']['aws']['cloudfront']['compress'],
            'headers': context['project']['aws']['cloudfront']['headers'],
            'default-ttl': context['project']['aws']['cloudfront']['default-ttl'],
            'errors': errors,
            'origins': OrderedDict([
                (o_id, {'hostname': parameterize(o['hostname']), 'pattern': o.get('pattern')})
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
    else:
        return host + '.' + default_main # something + '.' + elifesciences.org

def build_context_subdomains(context):
    context['subdomains'] = [complete_domain(s, context['project']['domain']) for s in context['project']['aws'].get('subdomains', [])]

def build_context_elasticache(context):
    if 'elasticache' in context['project']['aws']:
        context['elasticache'] = context['project']['aws']['elasticache']

def choose_config(stackname):
    (pname, instance_id) = core.parse_stackname(stackname)
    pdata = project.project_data(pname)
    more_context = {
        'stackname': stackname,
    }
    if instance_id in project.project_alt_config_names(pdata):
        LOG.info("using alternate AWS configuration %r", instance_id)
        # TODO there must be a single place where alt-config is switched in
        # hopefully as deep in the stack as possible to hide it away
        more_context['alt-config'] = instance_id

    return more_context
#
#
#

def render_template(context, template_type='aws'):
    pname = context['project_name']
    if template_type not in context['project']:
        raise ValueError("could not render an %r template for %r: no %r context found" %
                         (template_type, pname, template_type))
    if template_type == 'aws':
        return trop.render(context)

def write_template(stackname, contents):
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    open(output_fname, 'w').write(contents)
    return output_fname

def read_template(stackname):
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    return json.load(open(output_fname, 'r'))

def validate_aws_template(pname, rendered_template):
    conn = core.connect_aws_with_pname(pname, 'cfn')
    return conn.validate_template(rendered_template)

def more_validation(json_template_str):
    try:
        data = json.loads(json_template_str)
        # case: when "DBInstanceIdentifier" == "lax--temp2"
        # The parameter Filter: db-instance-id is not a valid identifier. Identifiers must begin with a letter;
        # must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.
        dbid = utils.lookup(data, 'Resources.AttachedDB.Properties.DBInstanceIdentifier', False)
        if dbid:
            assert '--' not in dbid, "database instance identifier contains a double hyphen: %r" % dbid

        return True
    except BaseException:
        LOG.exception("uncaught error attempting to validate cloudformation template")
        raise

def validate_project(pname, **extra):
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
#
#

def quick_render(project_name, **more_context):
    "generates a representative Cloudformation template for given project with dummy values"
    # set a dummy instance id if one hasn't been set.
    more_context['stackname'] = more_context.get('stackname', core.mk_stackname(project_name, 'dummy'))
    context = build_context(project_name, **more_context)
    return render_template(context)

#
#
#

def generate_stack(pname, **more_context):
    """given a project name and any context overrides, generates a Cloudformation
    stack file, writes it to file and returns a pair of (context, stackfilename)"""
    context = build_context(pname, **more_context)
    template = render_template(context)
    stackname = context['stackname']
    out_fname = write_template(stackname, template)
    context_handler.write_context(stackname, context)
    return context, out_fname

def regenerate_stack(pname, **more_context):
    current_template = bootstrap.current_template(more_context['stackname'])
    write_template(more_context['stackname'], json.dumps(current_template))
    context = build_context(pname, **more_context)
    delta_plus, delta_minus = template_delta(pname, context)
    return context, delta_plus, delta_minus


UPDATABLE_TITLE_PATTERNS = ['^CloudFront.*', '^ElasticLoadBalancer.*', '^EC2Instance.*', '.*Bucket$', '.*BucketPolicy', '^StackSecurityGroup$', '^ELBSecurityGroup$', '^CnameDNS.+$', '^AttachedDB$', '^AttachedDBSubnet$']
REMOVABLE_TITLE_PATTERNS = ['^CnameDNS\\d+$', '^ExtDNS$']
EC2_NOT_UPDATABLE_PROPERTIES = ['ImageId', 'Tags', 'UserData']

def template_delta(pname, context):
    """given an already existing template, regenerates it and produces a delta containing only the new resources.

    Most of the existing resources are treated as immutable and not put in the delta. Some that support updates like CloudFront are instead included"""
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
        if title_in_old['Type'] == 'AWS::EC2::Instance':
            for property_name in EC2_NOT_UPDATABLE_PROPERTIES:
                title_in_old['Properties'][property_name] = None
                title_in_new['Properties'][property_name] = None
        return title_in_old != title_in_new

    def legacy_title(title):
        # some titles were originally EC2Instance rather than EC2Instance1, EC2Instance2 and so on
        return title.strip("1234567890")

    delta_plus_resources = {
        title: r for (title, r) in template['Resources'].items()
        if (title not in old_template['Resources']
            and (legacy_title(title) not in old_template['Resources'])
            and ('EC2Instance' not in title))
        or (_title_is_updatable(title) and _title_has_been_updated(title, 'Resources'))
    }
    delta_plus_outputs = {
        title: o for (title, o) in template.get('Outputs', {}).items()
        if (title not in old_template['Outputs'] and not _related_to_ec2(o))
        or (_title_is_updatable(title) and _title_has_been_updated(title, 'Outputs'))
    }

    delta_minus_resources = {r: v for r, v in old_template['Resources'].iteritems() if r not in template['Resources'] and _title_is_removable(r)}
    delta_minus_outputs = {o: v for o, v in old_template['Outputs'].iteritems() if o not in template['Outputs']}

    return (
        {
            'Resources': delta_plus_resources,
            'Outputs': delta_plus_outputs,
        },
        {
            'Resources': delta_minus_resources,
            'Outputs': delta_minus_outputs,
        }
    )

def merge_delta(stackname, delta_plus, delta_minus):
    """Merges the new resources in delta in the local copy of the Cloudformation  template"""
    template = read_template(stackname)
    apply_delta(template, delta_plus, delta_minus)
    write_template(stackname, json.dumps(template))
    return template

def apply_delta(template, delta_plus, delta_minus):
    for component in delta_plus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized", component)
        data = template.get(component, {})
        data.update(delta_plus[component])
        template[component] = data
    for component in delta_minus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized", component)
        for title in delta_minus[component]:
            del template[component][title]
