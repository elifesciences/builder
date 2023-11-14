"""a collection of predicates that return either True or False

these should complement not replicate any project configuration validation."""

import os

import requests

from . import core, project


class AccessError(RuntimeError):
    pass

class StackAlreadyExistsError(RuntimeError):
    def __init__(self, message, stackname):
        RuntimeError.__init__(self, message)
        self.stackname = stackname

def http_access(url):
    timeout = 10 # seconds
    resp = requests.head(url, allow_redirects=True, timeout=timeout)
    return resp.status_code == 200 # noqa: PLR2004

def ssh_access(url):
    cmd = 'git ls-remote ' + url + ' &> /dev/null'
    return os.system(cmd) == 0

def access(repo_url):
    bits = repo_url.split('://', 1)
    just_protocol = 1
    protocol_and_address = 2
    if len(bits) == just_protocol:
        protocol = 'ssh'
        remote = repo_url
    else:
        assert len(bits) == protocol_and_address, "could not find a protocol in url: %r" % repo_url
        protocol, remote = bits
    if protocol == 'http':
        protocol = 'https'
    return {
        'https': http_access,
        'ssh': ssh_access,
    }[protocol](remote)

def can_access_builder_private(pname):
    "`True` if current user can access the private-repo for given project"
    pdata = project.project_data(pname)
    return access(pdata['private-repo'])

def ensure_can_access_builder_private(pname):
    if not can_access_builder_private(pname):
        pdata = project.project_data(pname)
        raise AccessError("failed to access the 'builder-private' repository: %s" % pdata['private-repo'])

def ensure_stack_does_not_exist(stackname):
    if core.stack_is_active(stackname):
        raise StackAlreadyExistsError("%s is an active stack" % stackname, stackname)
