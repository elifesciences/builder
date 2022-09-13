import copy
from buildercore import utils
from buildercore.utils import ensure
from buildercore.config import CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT
from kids.cache import cache as cached
import logging
LOG = logging.getLogger(__name__)

def read_project_file(project_file_path):
    """reads the contents of the YAML file at `project_file_path`.
    for example, `/path/to/builder/projects/elife.yaml`."""
    return utils.yaml_load(open(project_file_path, 'r'))

@cached
def all_projects(project_file_path):
    """returns a pair of `(project data defaults map, project data list)`.
    project data at `project_file_path` *must* contain a `defaults` section as the first entry."""
    allp = read_project_file(project_file_path)
    if allp is None:
        return ({}, [])
    ensure("defaults" in allp, "Project file %s is missing a `default` section" % (project_file_path,))
    defaults = allp.pop("defaults")
    return defaults, allp

#
#
#

def project_cloud_alt(project_alt_contents, project_base_cloud, global_cloud):
    cloud_alt = {}

    # handle the alternate configurations
    for altname, altdata in project_alt_contents.items():
        # take project's *current cloud state*,
        project_cloud = copy.deepcopy(project_base_cloud)

        # merge in any overrides
        utils.deepmerge(project_cloud, altdata)

        # merge this over top of original cloud defaults
        orig_defaults = copy.deepcopy(global_cloud)

        utils.deepmerge(orig_defaults, project_cloud, CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT)
        cloud_alt[str(altname)] = orig_defaults

    return cloud_alt

# TODO: have this accept a map of defaults and a list of project data maps,
# rather than read from `all_projects`.
def project_data(pname, project_file):
    "does a deep merge of defaults+project data with a few exceptions"

    global_defaults, project_list = all_projects(project_file)

    # exceptions.
    excluding = [
        'aws',
        'vagrant',
        'aws-alt',
        'gcp-alt',
        {'aws': CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT},
    ]
    pdata = copy.deepcopy(global_defaults)
    utils.deepmerge(pdata, project_list[pname], excluding)

    # handle the alternate configurations
    pdata['aws-alt'] = project_cloud_alt(
        pdata.get('aws-alt', {}),
        pdata.get('aws', {}),
        global_defaults['aws']
    )
    pdata['gcp-alt'] = project_cloud_alt(
        pdata.get('gcp-alt', {}),
        pdata.get('gcp', {}),
        global_defaults['gcp']
    )
    return pdata

def projects_from_file(path_to_file, *args, **kwargs):
    "returns a map of {path_to_file: project data} for given `path_to_file`."
    _, project_list = all_projects(path_to_file)

    # lsh@2022-09-05: removed OrderedDicts as we're now using python3.8 exclusively.
    pdata = {pname: project_data(pname, path_to_file) for pname in project_list}
    return {path_to_file: pdata}
