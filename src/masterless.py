import os
from collections import OrderedDict
from fabric.api import task
from decorators import requires_aws_stack
from buildercore import bootstrap, core, context_handler

import logging

LOG = logging.getLogger(__name__)

'''
# work, but not being used
def requires_master_server_access(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        import master
        ensure(master.server_access(), "this command requires access to the master server. you don't have it.")
        return fn(*args, **kwargs)
    return wrapper

def requires_masterless(fn):
    @wraps(fn)
    def wrapper(stackname=None, *args, **kwargs):
        ctx = context_handler.load_context(stackname)
        ensure(stackname and ctx['project']['aws']['ec2']['masterless'], "this command requires a masterless instance.")
        return fn(stackname, *args, **kwargs)
    return wrapper

@task
@requires_aws_stack
def ssh(stackname, node=None):
    "maintenance ssh. uses the pem key and the bootstrap user to login."
    import cfn
    instances = core.find_ec2_instances(stackname)
    public_ip = cfn._pick_node(instances, node).ip_address
    # -i identify file
    local("ssh %s@%s -i %s" % (config.BOOTSTRAP_USER, public_ip, core.stack_pem(stackname)))
'''

@task
@requires_aws_stack
def set_versions(stackname, *repolist):
    "call with formula name and a revision, like: builder-private@ab87af78asdf2321431f31"
    ctx = context_handler.load_context(stackname)

    pdata = ctx['project']
    known_formulas = pdata.get('formula-dependencies', [])
    known_formulas.extend([
        pdata['formula-repo'],
        pdata['private-repo']
    ])

    known_formula_map = OrderedDict(zip(map(os.path.basename, known_formulas), known_formulas))

    if not repolist:
        return 'nothing to do'

    arglist = []
    for user_string in repolist:
        if '@' not in user_string:
            print 'skipping %r, no revision component' % user_string
            continue

        repo, rev = user_string.split('@')

        if not rev.strip():
            print 'skipping %r, empty revision component' % user_string
            continue

        if repo not in known_formula_map:
            print 'skipping %r, unknown formula. known formulas: %s' % (repo, ', '.join(known_formula_map.keys()))
            continue

        arglist.append((repo, known_formula_map[repo], rev))

    if not arglist:
        return 'nothing to do'

    with core.stack_conn(stackname):
        for repo, formula, revision in arglist:
            bootstrap.run_script('update-master-formula.sh', repo, formula, revision)
