# from . import core # DONT import core. this project module should be relatively independent
import os
from buildercore import utils, config
from kids.cache import cache
from . import files
import copy
import logging
from functools import reduce

LOG = logging.getLogger(__name__)

#
# project data utilities
#

def set_project_alt(pdata, env, altkey):
    "non-destructive update of given project data with the specified alternative configuration."
    assert env in ['vagrant', 'aws', 'gcp'], "'env' must be either 'vagrant' or 'aws'"
    env_key = env + '-alt'
    assert altkey in pdata[env_key], "project has no alternative config %r. Available: %s" % (altkey, list(pdata[env_key].keys()))
    pdata_copy = copy.deepcopy(pdata) # don't modify the data given to us
    pdata_copy[env] = pdata[env_key][altkey]
    return pdata_copy

def _parse_path(project_path):
    """converts a given path into zero or many paths.
    if `project_path` does not exist, it will be discarded with a warning.
    if `project_path` is a directory containing `.yaml` files, each `.yaml` file will be returned."""
    path = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.exists(path):
        LOG.warning("project path not found, skipping: %s", path)
        return
    if os.path.isdir(path):
        return utils.listfiles(path, ['.yaml'])
    return [path]

def parse_path_list(project_path_list):
    """convert the list of project configuration paths to a list of (protocol, host, path) triples.
    local paths that point to directories will be expanded to include all project.yaml inside it.
    duplicate paths and paths that do not exist are removed."""
    path_list = []
    for path in project_path_list:
        path_list.extend([pp for pp in _parse_path(path) if pp])

    # remove any duplicates. may happen when expanding a directory of files.
    path_list = utils.unique(path_list)

    return path_list

@cache
def _project_map(project_locations_list=None):
    """returns a single map of all projects and their data"""
    def merge(orderedDict1, orderedDict2):
        orderedDict1.update(orderedDict2)
        return orderedDict1

    # a list of triples
    # [(protocol, host, path), ('file', None, '/path/to/projects.yaml'), ...]
    project_locations_list = parse_path_list(config.PROJECTS_FILES)

    # a list of parsed project data
    # [{'/path/to/projects.yaml': {'project1': {...}, 'project2': {...}, ...}, {'/path/to/another-projects.yaml': {...}}, ...]
    data = [files.projects_from_file(path) for path in project_locations_list]

    # a single map of paths to parsed project data
    # {'/path/to/projects.yaml': {'project1': {...}, 'project2': {...}, ...}, '/path/to/another-projects.yaml': {...}, ...}
    data = reduce(merge, data)

    # a list of parsed project data.
    # [{'project1': {...}, 'project2': {...}, ...}, {...}, ...]
    data = data.values()

    # a single map of parsed project data.
    # {'project1': {...}, 'project2': {...}, ...}
    return reduce(merge, data)

def project_map(project_locations_list=None):
    """returns a single map of all projects and their data.
    the returned value is a deepcopy of the cached `_project_map` data.

    `cfngen.build_context` is one of probably many functions modifying the project data,
    unintentionally modifying it for all subsequent accesses including during tests.

    this approach should be safer and avoid the speed problems with parsing the project
    files again at the cost of a deepcopy."""
    return utils.deepcopy(_project_map(project_locations_list))

def project_list():
    "returns a single list of projects, ignoring organization and project data"
    return list(project_map().keys())

def project_data(pname):
    "returns the data for a single project."
    data = project_map()
    try:
        return data[pname]
    except KeyError:
        raise ValueError("unknown project %r, known projects %r" % (pname, list(data.keys())))

#
#
#

def filtered_projects(filterfn, *args, **kwargs):
    "returns a dict of projects filtered by given filterfn)"
    return utils.dictfilter(filterfn, project_map(*args, **kwargs))

def branch_deployable_projects(*args, **kwargs):
    "returns a pair of (defaults, dict of projects with a repo)"
    return filtered_projects(lambda pname, pdata: 'repo' in pdata, *args, **kwargs)

def projects_with_formulas(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: pdata.get('formula-repo'), *args, **kwargs)

def aws_projects(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: 'aws' in pdata, *args, **kwargs)

def ec2_projects(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: pdata.get('aws', {}).get('ec2'), *args, **kwargs)

#
#
#

def project_formulas():
    def fn(pname, pdata):
        return [pdata.get('formula-repo')] + pdata.get('formula-dependencies', [])
    return utils.dictmap(fn, project_map())

#
#
#

def known_formulas():
    "a simple list of all known project formulas"
    return utils.lfilter(None, utils.unique(utils.shallow_flatten(project_formulas().values())))
