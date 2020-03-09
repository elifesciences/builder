import os, copy
from os.path import join
from collections import OrderedDict
from buildercore import utils
from buildercore.config import CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT
from kids.cache import cache as cached
import logging
LOG = logging.getLogger(__name__)

def read_project_file(project_file):
    "reads the contents of the YAML project file"
    return utils.ordered_load(open(project_file, 'r'))

@cached
def all_projects(project_file):
    allp = read_project_file(project_file)
    if allp is None:
        return ({}, [])
    assert "defaults" in allp, ("Project file %s is missing a `default` section" % project_file)
    defaults = allp.pop("defaults")
    return defaults, allp

#
#
#

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

def project_cloud_alt(project_alt_contents, project_base_cloud, global_cloud):
    cloud_alt = OrderedDict()

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

def project_file_name(project_file):
    "returns the name of the project file without the extension"
    fname = os.path.splitext(project_file)[0]
    return os.path.basename(fname)

def project_dir_path(project_file):
    # /path/to/elife-builder/project/elife.yaml =>
    # /path/to/elife-builder/project/elife/
    path = join(os.path.dirname(project_file), project_file_name(project_file))
    if not os.path.exists(path):
        # this call fails non-deterministically in build, debugging it

        try:
            os.mkdir(path)
        except BaseException:
            import subprocess
            print("Debugging os.mkdir(path) failure")
            print(subprocess.check_output(["ls", "-l", os.path.dirname(path)], stderr=subprocess.STDOUT))
            raise
    return path

def projects_from_file(path_to_file, *args, **kwargs):
    "returns a map of {org => project data} for a given file"
    orgname = project_file_name(path_to_file)
    _, project_list = all_projects(path_to_file)

    pdata = map(lambda pname: project_data(pname, path_to_file), project_list)
    pdata = OrderedDict(zip(project_list, pdata))
    return OrderedDict({orgname: pdata})
