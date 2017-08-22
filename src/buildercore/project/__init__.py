# from . import core # DONT import core. this project module should be relatively independent
from collections import OrderedDict
from buildercore import utils, config
from buildercore.decorators import osissue
from kids.cache import cache
from . import files

import copy

import logging
from functools import reduce
LOG = logging.getLogger(__name__)

#
# project data utilities
#

def project_alt_config_names(pdata, env='aws'):
    "returns names of all alternate configurations for given project data and environment (default aws)"
    assert env in ['vagrant', 'aws'], "'env' must be either 'vagrant' or 'aws'"
    return pdata.get(env + '-alt', {}).keys()

def set_project_alt(pdata, env, altkey):
    "non-destructive update of given project data with the specified alternative configuration."
    assert env in ['vagrant', 'aws'], "'env' must be either 'vagrant' or 'aws'"
    env_key = env + '-alt'
    assert altkey in pdata[env_key], "project has no alternative config %r" % altkey
    pdata_copy = copy.deepcopy(pdata) # don't modify the data given to us
    pdata_copy[env] = pdata[env_key][altkey]
    return pdata_copy

#
# unimplemented
#

# the intent of this function was to update a project's config and then save it back
# this is fine for files, but not remotes.
# there will be a class of projects of that cannot be updated

@osissue("this or something like this needs to be implemented")
def update_project_file(*args, **kwargs):
    raise NotImplementedError()

@osissue("how is this different from `update_project_file`?")
def write_project_file(new_project_file):
    raise NotImplementedError()


#
#
#

def find_project(project_location_triple):
    "given a triple of (protocol, hostname, path) returns a map of {org => project data}"
    plt = project_location_triple
    assert utils.iterable(plt), "given triple must be a collection of three values"
    assert len(project_location_triple) == 3, "triple must contain three values. got: %r" % project_location_triple
    protocol, hostname, path = plt
    fnmap = {
        #'file': OrgFileProjects,
        'file': files.projects_from_file,
        #'ssh': RemoteBuilderProjects,
        #'https': RemoteBuilderProjects,
    }
    if not protocol in fnmap.keys():
        LOG.info("unhandled protocol %r for %r" % (protocol, plt))
        return {}  # OrderedDict({})
    return fnmap[protocol](path, hostname)

def org_project_map(project_locations_list=None):
    """returns a merged map of {org => project data} after inspecting each location
    in given list duplicate projects in the same organisation will be merged."""
    if not project_locations_list:
        project_locations_list = config.app()['project-locations']

    def merge(p1, p2):
        utils.deepmerge(p1, p2)
        return p1
    data = map(find_project, project_locations_list)
    return reduce(merge, data)

def org_map(project_locations_list=None):
    "returns a map of {org => project names} excluding project data"
    opm = org_project_map(project_locations_list)
    return {org: pdata.keys() for org, pdata in opm.items()}

@cache
def project_map(project_locations_list=None):
    """returns a single map of all projects and their data, ignoring organizations
    overwriting any duplicates"""
    # ll: {'elife': {'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}},
    #      'barorg': {'example': {}}}
    opm = org_project_map(project_locations_list)
    # ll: [{'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}}], {'example': {}}]
    data = opm.values()
    # ll: {'lax': {...}, 'metrics': {...}, 'example': {...}}

    def merge(p1, p2):
        utils.deepmerge(p1, p2)
        return p1
    return reduce(merge, data)

def project_list(project_locations_list=None):
    "returns a single list of projects, ignoring organization and project data"
    return project_map(project_locations_list).keys()

def project_data(pname, project_locations_list=None):
    "returns the data for a single project"
    data = project_map(project_locations_list)
    try:
        return data[pname]
    except KeyError:
        raise ValueError("unknown project %r, known projects %r", pname, data.keys())

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

def all_formulas():
    formulas = OrderedDict()
    for pname in projects_with_formulas():
        pdata = project_data(pname)
        formulas[pname] = pdata['formula-repo']
    return formulas

def aws_projects(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: 'aws' in pdata, *args, **kwargs)
