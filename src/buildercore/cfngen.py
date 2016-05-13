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

        'instance_id': None, # must be provided by whatever is calling this
        'db_instance_id': None, # generated from the instance_id
        'branch': project_data['default-branch'],
        'revision': None, # may be used in future to checkout a specific revision of project
    }
    context = copy.deepcopy(defaults)
    context.update(more_context)

    assert context['instance_id'] != None, "an 'instance_id' wasn't provided."

    # alpha-numeric only
    default_db_instance_id = slugify(context['instance_id'], separator="")

    # ll: master.lax
    hostname = core.mk_hostname(context['instance_id'])
    # ll: master.lax.elifesciences.org
    full_hostname = "%(host)s.%(domain)s" % {'host': hostname if hostname else None,
                                            'domain': project_data.get('domain')}
    # ll: lax.elifesciences.org
    project_hostname = "%(sub)s.%(domain)s" % {'sub': project_data.get('subdomain') if hostname else None,
                                               'domain': project_data.get('domain')}

    # post-processing
    context.update({
        'db_instance_id': context['db_instance_id'] or default_db_instance_id,
        'is_prod_instance': context['instance_id'].split('-')[-1] in ['master', 'production'],

        'hostname': hostname, # ll: develop.lax
        'full_hostname': full_hostname, # ll: develop.lax.elifesciences.org
        'project_hostname': project_hostname, # ll: lax.elifesciences.org
    })

    # the above context will reside on the server at /etc/build_vars.json.b64
    # this gives Salt all (most) of the data that was available at template compile time.
    # part of the bootstrap process writes a file called /etc/cfn-info.json
    # this gives Salt the outputs available at stack creation
    context['build_vars'] = base64.b64encode(json.dumps(context))

    return context
#
#
#

def render_template(context):
    return trop.render(context)

def write_template(stackname, contents):
    output_fname = os.path.join(STACK_DIR, stackname + ".json")
    open(output_fname, 'w').write(contents)
    return output_fname

def quick_render(project, **more_context):
    "generates a representative Cloudformation template for given project with dummy values"
    # set a dummy instance id if one hasn't been set.
    more_context['instance_id'] = more_context.get('instance_id', project + '-dummy')
    context = build_context(project, **more_context)
    return render_template(context)

def quick_render_all(**more_context):
    "generates a representative Cloudformation template for all projects with dummy values"
    #return [(project, quick_render(project, **more_context)) for project in core.project_list()]
    return [(project, quick_render(project, **more_context)) for project in project.project_list()]

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
