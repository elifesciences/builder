from . import project
from .project import repo

def can_access_builder_private(pname):
    "returns True if current user can access the private-repo for given project"
    pdata = project.project_data(pname)
    return repo.access(pdata['private-repo'])
