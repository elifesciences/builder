"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, deffile, requires_aws_stack, timeit
import utils
from buildercore import core, bootstrap, cfngen, project
from buildercore.concurrency import concurrency_for
import cfn
import buildvars

import logging

LOG = logging.getLogger(__name__)

def impose_ordering(branch_list):
    branch_list, removed = utils.rmval(branch_list, 'master', 'develop')
    branch_list.sort()
    branch_list = removed + branch_list
    return branch_list

#
#
#

@task
@requires_branch_deployable_project
@echo_output
@timeit
def deploy(pname, instance_id=None, branch='master', part_filter=None):
    pdata = project.project_data(pname)
    if not branch:
        branch_list = utils.git_remote_branches(pdata['repo'])
        branch_list = impose_ordering(branch_list)
        branch = utils._pick('branch', branch_list, deffile('.branch'))
    stackname = cfn.generate_stack_from_input(pname, instance_id)

    region = pdata['aws']['region']
    active_stacks = core.active_stack_names(region)
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = cfngen.choose_config(stackname)
        more_context['branch'] = branch
        cfngen.generate_stack(pname, **more_context)

    bootstrap.create_update(stackname, part_filter)
    setdefault('.active-stack', stackname)


@task
@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None, concurrency='serial'):
    buildvars.switch_revision(stackname, revision)
    bootstrap.update_stack(stackname, concurrency=concurrency_for(stackname, concurrency))
