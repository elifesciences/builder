from fabric.api import task, local
from buildercore import project
import utils
import sys
import logging
LOG = logging.getLogger(__name__)

def vault_addr():
    defaults, _ = project.raw_project_map()
    return defaults['aws']['vault']['address']

@task
def login():
    cmd = "VAULT_ADDR=%s vault login" % vault_addr()
    local(cmd)

@task
def logout():
    cmd = "rm -f ~/.vault-token"
    local(cmd)

@task
def lookup(token):
    cmd = "VAULT_ADDR=%s VAULT_TOKEN=%s vault token lookup" % (vault_addr(), token)
    local(cmd)

@task
def create_token():
    fname = utils.get_input('first name: ')
    lname = utils.get_input('last name: ')
    if not (fname and lname):
        print("a firstname and a surname are required")
        sys.exit(1)
    name = "".join(x.title() for x in [fname, lname])
    cmd = "VAULT_ADDR=%s vault token create -policy=builder-user -display-name=%s" % (vault_addr(), name)
    local(cmd)

@task
def revoke_token(token):
    cmd = "VAULT_ADDR=%s vault token revoke %s" % (vault_addr(), token)
    local(cmd)
