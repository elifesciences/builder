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
from . import utils, trop, core, config
from .config import STACK_DIR

# project names in projects file don't match the names found
# in the pillar data. this describes the lookups so that key
# replacement can happen. urgh. fix/remove/whatever.
PILLAR_NAMES_TO_PROJECT_NAMES = {
    # pillar -> project
    'elife_website': 'elife-website',
    'elife_metrics': 'elife-metrics',
    'elife_dashboard': 'elife-dashboard',
    'lax': 'elife-lax'}

def salt_pillar_data(*dir_list):
    "reads in the Salt pillar data "
    def _merge(x, y):
        x.update(y)
        return x
    def is_sls(fname):
        return os.path.isfile(fname) and os.path.splitext(fname)[1] == '.sls'            
    dir_data = {}
    for ddir in filter(os.path.isdir, filter(None, dir_list)):
        file_list = map(lambda fname: os.path.join(ddir, fname), os.listdir(ddir))
        sls_list = filter(is_sls, file_list)
        many_json = map(utils.yaml_to_json, sls_list)
        many_dict = map(json.loads, many_json)
        if many_dict:
            dir_data.update(reduce(_merge, many_dict))
    # replace the keys with proper project names
    [utils.renkey(dir_data, pillar_key, project_key) for pillar_key, project_key in PILLAR_NAMES_TO_PROJECT_NAMES.items()]
    return dir_data

def build_context(pname, project_file, salt_pillar_dir, **more_context):
    """wrangles parameters into a dictionary (context) that can be given to
    whatever renders the final template"""

    defaults, supported_projects = core.read_projects(project_file)
    assert pname in supported_projects, "Unknown project %r" % pname

    pillar_data = salt_pillar_data(salt_pillar_dir)
    project_data = core.project_data(pname, project_file)

    if 'alt-config' in more_context:
        project_data = core.set_project_alt(project_data, 'aws', more_context['alt-config'])
    
    defaults = {
        'pillar': pillar_data, # all pillar data

        'project_name': pname,
        'project': project_data,
        'project_pillar': pillar_data.get(pname, {}),

        'author': os.environ.get("LOGNAME") or os.getlogin(),
        'date_rendered': utils.ymd(),

        'instance_id': None, # must be provided by whatever is calling this
        'db_instance_id': None, # generated from the instance_id
        'branch': 'master',
    }
    context = copy.deepcopy(defaults)
    context.update(more_context)
    
    assert context['instance_id'] != None, "an 'instance_id' wasn't provided."

    # alpha-numeric only
    default_db_instance_id = slugify(context['instance_id'], separator="") 

    hostname = core.mk_hostname(pname, context['instance_id'], project_file)
    full_hostname = "%s.elifesciences.org" % hostname if hostname else None
    project_hostname = "%s.elifesciences.org" % project_data.get('subdomain') if hostname else None

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
    exclude_these = ['pillar', 'project_pillar']
    unencoded_context = utils.exsubdict(context, exclude_these)
    encoded_context = base64.b64encode(json.dumps(unencoded_context))
    context['build_vars'] = encoded_context

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
    context = build_context(project, config.PROJECT_FILE, config.PILLAR_DIR, **more_context)
    return render_template(context)

def quick_render_all(**more_context):
    "generates a representative Cloudformation template for all projects with dummy values"
    return [(project, quick_render(project, **more_context)) for project in core.project_list()]

#
#
#

def generate_stack(pname, **more_context):
    """given a project name and any context overrides, generates a Cloudformation
    stack file, writes it to file and returns a pair of (context, stackfilename)"""
    context = build_context(pname, config.PROJECT_FILE, config.PILLAR_DIR, **more_context)
    template = render_template(context)
    stackname = context['instance_id']
    out_fname = write_template(stackname, template)
    return context, out_fname
