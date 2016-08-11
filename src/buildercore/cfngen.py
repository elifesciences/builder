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

import os, json, base64, copy
from slugify import slugify
from . import utils, trop, core, config, project
from .config import STACK_DIR
from .decorators import osissue, osissuefn

import logging

LOG = logging.getLogger(__name__)

def build_context(pname, **more_context):
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

        # when this was first introduced, instance_id was synonmous with stackname
        'instance_id': None, # must be provided by whatever is calling this


        'branch': project_data.get('default-branch'),
        'revision': None, # may be used in future to checkout a specific revision of project
        'rds_dbname': None, # generated from the instance_id when present
        'rds_username': None, # could possibly live in the project data, but really no need.
        'rds_password': None,
        'rds_instance_id': None,
    }

    context = copy.deepcopy(defaults)
    context.update(more_context)

    assert context['instance_id'] != None, "an 'instance_id' wasn't provided."
    stackname = context['instance_id']

    # alpha-numeric only
    # TODO: investigate possibility of ambiguous RDS naming here

    # hostname data
    context.update(core.hostname_struct(stackname))
    
    # post-processing
    if context['project']['aws'].has_key('rds'):
        default_rds_dbname = slugify(stackname, separator="")
        context.update({
            'rds_username': 'root',
            'rds_password': utils.random_alphanumeric(length=32), # will be saved to buildvars.json
            'rds_dbname': context.get('rds_dbname') or default_rds_dbname, # *must* use 'or' here
            'rds_instance_id': slugify(stackname), # *completely* different to database name
        })

    # is this a production instance? if yes, then we'll do things like tweak the dns records ...
    context.update({
        'is_prod_instance': core.is_prod_stack(stackname),
    })

    # the above context will reside on the server at /etc/build_vars.json.b64
    # this gives Salt all (most) of the data that was available at template compile time.
    # part of the bootstrap process writes a file called /etc/cfn-info.json
    # this gives Salt the outputs available at stack creation
    context['build_vars'] = base64.b64encode(json.dumps(context)) if context['project']['aws']['ec2'] else None

    return context

#
#
#

def render_template(context, template_type='aws'):
    pname = context['project_name']
    if not context['project'].has_key(template_type):
        raise ValueError("could not render an %r template for %r: no %r context found" % \
                             (template_type, pname, template_type))
    if template_type == 'aws':
        return trop.render(context)

def write_template(stackname, contents):
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    open(output_fname, 'w').write(contents)
    return output_fname

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
        resp = validate_aws_template(pname, template)
        more_validation(template)
        # validate all alternative configurations
        for altconfig in pdata.get('aws-alt', {}).keys():
            LOG.info('validating %s, %s' % (pname, altconfig))
            extra = {
                'alt-config': altconfig
            }
            template = quick_render(pname, **extra)
            validate_aws_template(pname, template)
            time.sleep(0.5) # be nice, avoid any rate limiting

    except boto.connection.BotoServerError:
        msg = "failed:\n" + template + "\n%s (%s) template failed validation" % (pname, altconfig if altconfig else 'normal')
        LOG.error(msg)
        return False

    except:
        msg = "unhandled fail:\n" + template + "\n%s (%s) template failed validation" % (pname, altconfig if altconfig else 'normal')
        LOG.exception(msg)
        return False

    return True

#
# 
#

def quick_render(project, **more_context):
    "generates a representative Cloudformation template for given project with dummy values"
    # set a dummy instance id if one hasn't been set.
    more_context['instance_id'] = more_context.get('instance_id', project + '--dummy')
    context = build_context(project, **more_context)
    return render_template(context)

#
#
#

def generate_stack(pname, **more_context):
    """given a project name and any context overrides, generates a Cloudformation
    stack file, writes it to file and returns a pair of (context, stackfilename)"""
    context = build_context(pname, **more_context)
    template = render_template(context)
    stackname = context['instance_id']
    out_fname = write_template(stackname, template)
    return context, out_fname
