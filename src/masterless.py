import os
from os.path import join
from collections import OrderedDict
from pprint import pformat
from fabric.api import task, lcd, settings
from fabric.operations import local
from decorators import requires_project
from buildercore import bootstrap, checks, core, context_handler, config
from buildercore.utils import ensure
import logging
import cfn
from functools import wraps

LOG = logging.getLogger(__name__)

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


#
#
#

def parse_validate_repolist(pdata, *repolist):
    "returns a list of triples"
    known_formulas = pdata.get('formula-dependencies', [])
    known_formulas.extend([
        pdata['formula-repo'],
        pdata['private-repo']
    ])

    known_formula_map = OrderedDict(zip(map(os.path.basename, known_formulas), known_formulas))

    arglist = []
    for user_string in repolist:
        if '@' not in user_string:
            print('skipping %r, no revision component' % user_string)
            continue

        repo, rev = user_string.split('@')

        if not rev.strip():
            print('skipping %r, empty revision component' % user_string)
            continue

        if repo not in known_formula_map:
            print('skipping %r, unknown formula. known formulas: %s' % (repo, ', '.join(known_formula_map.keys())))
            continue

        arglist.append((repo, known_formula_map[repo], rev))

    # test given revisions actually exist in formulas
    for name, _, revision in arglist:
        path = join(config.PROJECT_PATH, "cloned-projects", name)
        if not os.path.exists(path):
            LOG.warn("couldn't find formula %r locally, revision check skipped", path)
            continue

        with lcd(path), settings(warn_only=True):
            ensure(local("git fetch --quiet").succeeded, "failed to fetch remote refs for %s" % path)
            ensure(local("git cat-file -e %s^{commit}" % revision).succeeded, "failed to find ref %r in %s" % (revision, name))

    return arglist

#
#

@task
@requires_project
@requires_master_server_access
def launch(pname, instance_id=None, alt_config='standalone', *repolist):
    stackname = cfn.generate_stack_from_input(pname, instance_id, alt_config)
    pdata = core.project_data_for_stackname(stackname)
    # ensure given alt config has masterless=True
    ensure(pdata['aws-alt'], "project has no alternate configurations")
    ensure(alt_config in pdata['aws-alt'], "unknown alt-config %r" % alt_config)
    ensure(pdata['aws-alt'][alt_config]['ec2']['masterless'], "alternative configuration %r has masterless=False" % alt_config)

    formula_revisions = parse_validate_repolist(pdata, *repolist)

    LOG.info('attempting to create masterless stack:')
    LOG.info('stackname:\t' + stackname)
    LOG.info('region:\t' + pdata['aws']['region'])
    LOG.info('formula_revisions:\t%s' % pformat(formula_revisions))

    if core.is_master_server_stack(stackname):
        checks.ensure_can_access_builder_private(pname)
    checks.ensure_stack_does_not_exist(stackname)

    bootstrap.create_stack(stackname)

    LOG.info('updating stack %s', stackname)
    bootstrap.update_stack(stackname, service_list=['ec2', 'sqs', 's3'], formula_revisions=formula_revisions)

#
#
#

@task
@requires_master_server_access
@requires_masterless
def set_versions(stackname, *repolist):
    "call with formula name and a revision, like: builder-private@ab87af78asdf2321431f31"
    ctx = context_handler.load_context(stackname)
    repolist = parse_validate_repolist(ctx['project'], *repolist)

    if not repolist:
        return 'nothing to do'

    def updater():
        for repo, formula, revision in repolist:
            bootstrap.run_script('update-masterless-formula.sh', repo, formula, revision)

    core.stack_all_ec2_nodes(stackname, updater, concurrency='serial')
