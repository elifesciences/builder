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

def find_project(project_location_triple):
    "given a triple of (protocol, hostname, path) returns a map of {org => project data}"
    plt = project_location_triple
    assert utils.iterable(plt), "given triple must be a collection of three values"
    assert len(project_location_triple) == 3, "triple must contain three values. got: %r" % project_location_triple
    protocol, hostname, path = plt
    fnmap = {
        # 'file': OrgFileProjects,
        'file': files.projects_from_file,
        # 'ssh': RemoteBuilderProjects,
        # 'https': RemoteBuilderProjects,
    }
    if not protocol in fnmap.keys():
        LOG.info("unhandled protocol %r for %r" % (protocol, plt))
        return {}  # OrderedDict({})
    return fnmap[protocol](path, hostname)

def _parse_path(project_path):
    "convert a path into a triple of (protocol, hostname, path)"
    bits = project_path.split('://', 1)
    if len(bits) == 2:
        # "http://example.org/path/to/org/file" => (http, example.org, '/path/to/org/file/')
        protocol, rest = bits
        host, path = rest.split('/', 1)
        return (protocol, host, '/' + path)

    # "/path/to/org/somefile" => (file, None, '/path/to/org/somefile')
    # "/path/to/org/somedir" => (dir, None, '/path/to/org/somedir/')
    path = os.path.abspath(os.path.expanduser(project_path))
    protocol = 'file' if os.path.isfile(path) else 'dir'
    host = None
    return (protocol, host, path)

def _expand_dir_path(triple):
    "any yaml files in any given directories will be found and used"
    protocol, host, path = triple
    if protocol in ['dir', 'file'] and not os.path.exists(path):
        LOG.warning("could not resolve %r, skipping", path)
        return [None]
    if protocol == 'dir':
        return utils.lmap(_parse_path, utils.listfiles(path, ['.yaml']))
    return [triple]

def parse_path_list(path_list):
    """convert the list of project configuration paths to a list of (protocol, host, path) triples.
    local paths that point to directories will be expanded to include all project.yaml inside it.
    duplicate paths and paths that do not exist are removed."""

    # convert a list of paths to a list of triples
    path_list = utils.lmap(_parse_path, path_list)

    # we don't want dirs, we want files
    path_list = utils.shallow_flatten(map(_expand_dir_path, path_list))

    # remove any bogus values
    path_list = utils.lfilter(None, path_list)

    # remove any duplicates. can happen when we expand dir => files
    path_list = utils.unique(path_list)

    return path_list


@cache
def _project_map(project_locations_list=None):
    """returns a single map of all projects and their data"""
    def merge(orderedDict1, orderedDict2):
        orderedDict1.update(orderedDict2)
        return orderedDict1

    # [(protocol, host, path), ('file', None, '/path/to/projects.yaml'), ...]
    project_locations_list = parse_path_list(config.PROJECTS_FILES)

    # {'dummy-project1': {'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}},
    #  'dummy-project2': {'example': {}}}
    data = map(find_project, project_locations_list)
    opm = reduce(merge, data)

    # [{'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}}], {'example': {}}]
    data = opm.values()

    # {'lax': {...}, 'metrics': {...}, 'example': {...}}
    return reduce(merge, data)

def project_map(project_locations_list=None):
    """returns a deepcopy of the cached `_project_map` results.
    `cfngen.build_context` is one of probably many functions that are modifying the project data, unintentionally modifying it for all subsequent accesses, including during tests.
    this approach should be safer, avoid the speed problems with parsing the project files at the cost of a deepcopy."""
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
