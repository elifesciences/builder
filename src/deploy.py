"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, requires_aws_stack, timeit
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
def deploy(pname, instance_id=None, alt_config=None):
    pdata = project.project_data(pname)
    stackname = cfn.generate_stack_from_input(pname, instance_id, alt_config=alt_config)

    region = pdata['aws']['region']
    active_stacks = core.active_stack_names(region)
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = cfngen.choose_config(stackname)
        cfngen.generate_stack(pname, **more_context)

    bootstrap.create_update(stackname)
    setdefault('.active-stack', stackname)


@task
@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None, concurrency='serial'):
    buildvars.switch_revision(stackname, revision)
    bootstrap.update_stack(stackname, concurrency=concurrency_for(stackname, concurrency))
