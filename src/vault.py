from fabric.api import task, local
from buildercore import project
import utils
import sys
import logging
LOG = logging.getLogger(__name__)

def vault_addr():
    defaults, _ = project.raw_project_map()
    return defaults['aws']['vault']['address']

def vault_policy():
    return 'builder-user'

@task
def login():
    cmd = "VAULT_ADDR=%s vault login" % vault_addr()
    local(cmd)

@task
def logout():
    cmd = "rm -f ~/.vault-token"
    local(cmd)

@task
def token_lookup(token):
    cmd = "VAULT_ADDR=%s VAULT_TOKEN=%s vault token lookup" % (vault_addr(), token)
    local(cmd)

@task
def token_create():
    print("Warning: you should be authenticated with a root token to effectively create a new token here")
    token = utils.get_input('token display name: ')
    if not token or not token.strip():
        print("a token display name is required")
        sys.exit(1)
    cmd = "VAULT_ADDR=%s vault token create -policy=%s -display-name=%s" % (vault_addr(), vault_policy(), token)
    local(cmd)

@task
def token_revoke(token):
    cmd = "VAULT_ADDR=%s vault token revoke %s" % (vault_addr(), token)
    local(cmd)
