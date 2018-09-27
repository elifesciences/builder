"""a collection of predicates that return either True or False

these should compliment not replicate any project configuration validation."""

from . import core, project
from .project import repo

class AccessProblem(RuntimeError):
    pass

class StackAlreadyExistsProblem(RuntimeError):
    pass

def can_access_builder_private(pname):
    "True if current user can access the private-repo for given project"
    pdata = project.project_data(pname)
    return repo.access(pdata['private-repo'])

def ensure_can_access_builder_private(pname):
    if not can_access_builder_private(pname):
        pdata = project.project_data(pname)
        raise AccessProblem("failed to access your organisation's 'builder-private' repository: %s . You'll need access to this repository to add a deploy key later" % pdata['private-repo'])


def ensure_stack_does_not_exist(stackname):
    if core.stack_is_active(stackname):
        raise StackAlreadyExistsProblem("%s is an active stack" % stackname)

def requires_certificate(stackname):
    "True if the given stack has a subdomain but is not using a properly configured certificate"
    pass

def certificate_requires_renewal(stackname):
    "True if the certificate on the given stack expires in less than 28 days"
    pass

def vpc_id_exists(pname):
    "returns True if the vpc_id for the given project exists"
    pass

def subnet_id_exists(pname):
    "returns True if the subnet within the vpc exists"
    pass
