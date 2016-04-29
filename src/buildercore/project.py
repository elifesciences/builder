from . import core, utils, config
from .utils import unique, flatten
import logging
LOG = logging.getLogger(__name__)

class ProjectInterface(object):
    def __init__(self, path, host):
        self.path = path
        self.raw_host = host

    def project_list(self):
        "returns a map of organisations to project lists"
        raise NotImplementedError

    def project_config(self, orgname, pname):
        "returns the project configuration for a particular project for a particular organisation"
        raise NotImplementedError

class OrgFileProjects(ProjectInterface):
    """pull projects from an 'org file', a yaml file containing a list 
    of projects with the defaults for each project at the top of the file"""

    def orgname(self):
        return core.project_file_name(self.path)
    
    def project_list(self):
        return {self.orgname(): core.all_projects(self.path)[1].keys()}

    def project_config(self, orgname, pname):
        return core.project_data(pname)

class RemoteBuilderProjects(ProjectInterface):
    """pull project information from a remote instance of the builder"""
    pass

def _project_list(project_location_triple):
    plt = project_location_triple
    assert utils.iterable(plt), "given triple must be a collection of three values"
    assert len(project_location_triple) == 3, "triple must contain three values"
    protocol, hostname, path = plt
    x = {
        'file': OrgFileProjects,
        #'ssh': RemoteBuilderProjects,
        #'https': RemoteBuilderProjects,
    }
    if not protocol in x.keys():
        LOG.warn("unhandled protocol %r for %r" % (protocol, plt))
        return {}
    inst = x[protocol](path, hostname)
    return inst.project_list()

def org_project_map(project_locations_list=None):
    """returns a merged dictionary of organizations and their project lists.
    duplicate projects in the same organisation will be merged."""
    if not project_locations_list:
        project_locations_list = config.app()['project-locations']
    def merge(p1, p2):
        utils.deepmerge(p1, p2)
        return p1
    data = map(_project_list, project_locations_list)
    return reduce(merge, data)

def project_list(project_locations_list=None):
    "returns a single list of projects, ignoring which organization the project belongs to, removing any duplicates"
    opm = org_project_map(project_locations_list)
    return unique(flatten(opm.values()))
