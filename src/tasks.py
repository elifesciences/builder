"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be
better off in their own module. This module really is for stuff
that has no home."""
import os
from buildercore import core, bootstrap, bakery, lifecycle
from fabric.api import local
from utils import confirm, errcho, get_input
from decorators import requires_aws_stack
from buildercore.core import stack_conn
from buildercore.context_handler import load_context
import logging

LOG = logging.getLogger(__name__)

@requires_aws_stack
def create_ami(stackname, name=None):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r" % pname
    confirm(msg)

    amiid = bakery.create_ami(stackname, name)
    print(amiid)
    errcho('update project file with new ami %s. these changes must be merged and committed manually' % amiid)

#
#
#

def diff_builder_config():
    "helps keep three"
    file_sets = [
        [
            "./builder-private-example/pillar/elife.sls",
            "./cloned-projects/builder-base-formula/pillar/elife.sls",
            "./builder-private/pillar/elife.sls"
        ],
        [
            "./projects/elife.yaml",
            "./builder-private/projects/elife-private.yaml",
        ]
    ]
    for paths in file_sets:
        local("meld " + " ".join(paths))

@requires_aws_stack
def repair_cfn_info(stackname):
    with stack_conn(stackname):
        bootstrap.write_environment_info(stackname, overwrite=True)

@requires_aws_stack
def repair_context(stackname):
    # triggers the workaround of downloading it from EC2 and persisting it
    load_context(stackname)

@requires_aws_stack
def remove_minion_key(stackname):
    bootstrap.remove_minion_key(stackname)


def restart_all_running_ec2(statefile):
    "restarts all running ec2 instances. multiple nodes are restarted serially and failures prevent the rest of the node from being restarted"

    os.system("touch " + statefile)

    results = core.active_stack_names(core.find_region())

    u1404 = [
        'api-gateway',
        'journal',
        'search',
        'api-dummy',
        'medium',
    ]

    legacy = [
        'elife-api'
    ]

    dont_do = u1404 + legacy

    # order not preserved
    do_first = [
        'master-server',
        'bus',
        'elife-alfred',
        'elife-bot',
        'iiif',
    ]

    pname = lambda stackname: core.parse_stackname(stackname)[0]
    todo = sorted(results, key=lambda stackname: pname(stackname) in do_first, reverse=True)
    todo = filter(lambda stackname: pname(stackname) not in dont_do, todo)

    with open(statefile, 'r') as fh:
        done = fh.read().split('\n')

    with open(statefile, 'a') as fh:
        LOG.info('writing state to ' + fh.name)

        for stackname in todo:
            if stackname in done:
                LOG.info('skipping ' + stackname)
                continue
            try:
                LOG.info('restarting' + stackname)
                # only restart instances that are currently running
                # this will skip ci/end2end
                lifecycle.restart(stackname, initial_states='running')
                LOG.info('done' + stackname)
                fh.write(stackname + "\n")
                fh.flush()

            except BaseException:
                LOG.exception("unhandled exception restarting %s", stackname)
                LOG.warn("%s is in an unknown state", stackname)
                get_input('pausing, any key to continue, ctrl+c to quit')

        print
        print('wrote state to', fh.name)
