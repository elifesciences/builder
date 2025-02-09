import logging
import os
from collections import OrderedDict
from functools import wraps
from os.path import join
from pprint import pformat

import cfn
from buildercore import bootstrap, checks, config, context_handler, core
from buildercore.command import lcd, local, settings
from buildercore.utils import ensure, subdict
from decorators import requires_project

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
        ensure(stackname and ctx['ec2']['masterless'], "this command requires a masterless instance.")
        return fn(stackname, *args, **kwargs)
    return wrapper



def parse_validate_repolist(fdata, *repolist):
    "returns a list of triples"
    known_formulas = fdata.get('formula-dependencies', [])
    known_formulas.extend([
        fdata['formula-repo'],
        fdata['private-repo']
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
        path = join(config.CLONED_PROJECT_FORMULA_PATH, name)
        if not os.path.exists(path):
            LOG.warning("couldn't find formula %r locally, revision check skipped", path)
            continue

        with lcd(path), settings(warn_only=True):
            ensure(local("git fetch --quiet")['succeeded'], "failed to fetch remote refs for %s" % path)
            ensure(local("git cat-file -e %s^{commit}" % revision)['succeeded'], "failed to find ref %r in %s" % (revision, name))

    return arglist


@requires_project
@requires_master_server_access
def launch(pname, instance_id=None, alt_config='standalone', *repolist):
    stackname = cfn.generate_stack_from_input(pname, instance_id, alt_config)
    pdata = core.project_data_for_stackname(stackname)

    # ensure given alt config has masterless=True
    # todo: can the choices presented to the user remove non-masterless alt-configs?
    ensure(pdata['aws-alt'], "project has no alternate configurations")
    ensure(alt_config in pdata['aws-alt'], "unknown alt-config %r" % alt_config)
    ensure(pdata['aws-alt'][alt_config]['ec2']['masterless'], "alternative configuration %r has masterless=False" % alt_config)

    formula_revisions = parse_validate_repolist(pdata, *repolist)

    # todo: this is good UX but was simply debug output that got left in.
    # a better summary of what is to be created could be printed out,
    # preferably after the templates are printed out but before confirmation.
    LOG.info('attempting to create masterless stack:')
    LOG.info('stackname:\t%s', stackname)
    LOG.info('region:\t%s', pdata['aws']['region'])
    LOG.info('formula_revisions:\t%s', pformat(formula_revisions))

    if core.is_master_server_stack(stackname):
        checks.ensure_can_access_builder_private(pname)
    checks.ensure_stack_does_not_exist(stackname)

    bootstrap.create_stack(stackname)

    LOG.info('updating stack %s', stackname)
    bootstrap.update_stack(stackname, service_list=['ec2', 'sqs', 's3'], formula_revisions=formula_revisions)


@requires_master_server_access
@requires_masterless
def set_versions(stackname, *repolist):
    """Updates formulas on a masterless stack to a specific revision.
    call with formula name and a revision, like:
    'builder-private@ab87af78asdf2321431f31'"""

    context = context_handler.load_context(stackname)
    fkeys = ['formula-repo', 'formula-dependencies', 'private-repo', 'configuration-repo']
    fdata = subdict(context['project'], fkeys)
    repolist = parse_validate_repolist(fdata, *repolist)

    if not repolist:
        return 'nothing to do'

    def updater():
        for repo, formula, revision in repolist:
            bootstrap.run_script('update-masterless-formula.sh', repo, formula, revision)

    core.stack_all_ec2_nodes(stackname, updater, concurrency='serial')
    return None
