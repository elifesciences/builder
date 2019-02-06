# TODO: port most of src/vault.py in here

import json
import subprocess

def token_create(vault_addr, policy, display_name):
    # TODO: put a default of 24h for token lifetime rather than 768h?
    cmd = ["vault", "token", "create", "-address=%s" % vault_addr, "-policy=%s" % policy, "-display-name=%s" % display_name, "-format=json"]
    result = json.loads(subprocess.check_output(cmd))
    return result['auth']['client_token']
