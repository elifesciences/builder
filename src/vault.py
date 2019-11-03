from fabric.api import local
from buildercore import project
import utils
import sys
import logging
LOG = logging.getLogger(__name__)

def vault_addr():
    master = project.project_map()['master-server']
    return master['aws']['vault']['address']

def vault_policy():
    return 'builder-user'

def login():
    cmd = "VAULT_ADDR=%s vault login" % vault_addr()
    local(cmd)

def logout():
    cmd = "rm -f ~/.vault-token"
    local(cmd)

def policies_update():
    _warning_root_token()
    cmd = "VAULT_ADDR=%s vault policy write %s .vault/%s.hcl" % (vault_addr(), vault_policy(), vault_policy())
    local(cmd)

def token_lookup(token):
    cmd = "VAULT_ADDR=%s VAULT_TOKEN=%s vault token lookup" % (vault_addr(), token)
    local(cmd)

def token_list_accessors():
    _warning_root_token()
    cmd = "VAULT_ADDR=%s vault list auth/token/accessors" % (vault_addr())
    local(cmd)

def token_lookup_accessor(accessor):
    _warning_root_token()
    cmd = "VAULT_ADDR=%s vault token lookup -accessor %s" % (vault_addr(), accessor)
    local(cmd)

def token_create():
    _warning_root_token()
    token = utils.get_input('token display name: ')
    if not token or not token.strip():
        print("a token display name is required")
        sys.exit(1)
    cmd = "VAULT_ADDR=%s vault token create -policy=%s -display-name=%s" % (vault_addr(), vault_policy(), token)
    local(cmd)

def token_revoke(token):
    cmd = "VAULT_ADDR=%s vault token revoke %s" % (vault_addr(), token)
    local(cmd)

def _warning_root_token():
    print("Warning: you should probably be authenticated with a root token for this operation")
