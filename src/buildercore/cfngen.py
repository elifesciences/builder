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
from slugify import slugify
from . import utils, trop, core, project, context_handler
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
        'elb': False,
        'sns': [],
        'sqs': {},
        'ext': None
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
        # alpha-numeric only
        # TODO: investigate possibility of ambiguous RDS naming here
        context.update({
            'rds_username': 'root',
            'rds_password': utils.random_alphanumeric(length=32), # will be saved to build-vars.json
            'rds_dbname': context.get('rds_dbname') or default_rds_dbname, # *must* use 'or' here
            'rds_instance_id': slugify(stackname), # *completely* different to database name
        })

    if 'ext' in context['project']['aws']:
        context['ext'] = context['project']['aws']['ext']

    # is this a production instance? if yes, then we'll do things like tweak the dns records ...
    context.update({
        'is_prod_instance': core.is_prod_stack(stackname),
    })

    context['ec2'] = context['project']['aws'].get('ec2', True)

    if 'elb' in context['project']['aws']:
        if isinstance(context['project']['aws']['elb'], dict):
            context['elb'] = context['project']['aws']['elb']
        else:
            context['elb'] = {}
        context['elb'].update({
            'subnets': [
                context['project']['aws']['subnet-id'],
                context['project']['aws']['redundant-subnet-id']
            ]
        })

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

    if 's3' in context['project']['aws']['s3']:
        # at the moment, don't support any parameterization of names,
        # but if we start using {instance}, here is the place to replace it
        context['s3'] = context['project']['aws']['s3']

    return context


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
    with open(output_fname, 'r') as f:
        return json.loads(f.read())

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
    except:
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

def template_delta(pname, **more_context):
    """given an already existing template, regenerates it and produces a delta containing only the new resources.

    Existing resources are treated as immutable and not put in the delta"""
    old_template = read_template(more_context['stackname'])
    context = build_context(pname, **more_context)
    template = json.loads(render_template(context))
    return {
        'Outputs': {title:o for (title, o) in template['Outputs'].iteritems() if title not in old_template['Outputs']},
        'Resources': {title:r for (title, r) in template['Resources'].iteritems() if title not in old_template['Resources']}
    }

def merge_delta(stackname, delta):
    """Merges the new resources in delta in the local copy of the Cloudformation  template"""
    template = read_template(stackname)
    for component in delta:
        assert component in ["Resources", "Outputs"]
        for title in delta[component]:
            template[component].update(delta[component])
    write_template(stackname, json.dumps(template))
    return template

