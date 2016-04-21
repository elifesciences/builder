"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, deffile
import utils
from buildercore import core, bootstrap, cfngen

import logging

LOG = logging.getLogger(__name__)

def branch_stack_name(pname, branch):
    "given a project and a branch, returns an instance name"
    return "%(pname)s-%(branch)s" % locals()

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
def deploy(pname):
    pdata = core.project_data(pname)
    branch_list = utils.git_remote_branches(pdata['repo'])
    branch_list = impose_ordering(branch_list)    
    branch = utils._pick('branch', branch_list, deffile('.branch'))
    stackname = branch_stack_name(pname, branch)
    active_stacks = core.all_aws_stack_names()
    bootstrap.update_master()
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = {
            'instance_id': stackname,
            'branch': branch,
        }
        # tie branch names to alternate configurations
        if branch in core.project_alt_config_names(pdata):
            LOG.info("using alternate AWS configuration %r", branch)
            more_context['alt-config'] = branch
        cfngen.generate_stack(pname, **more_context)
        bootstrap.create_stack(stackname)
    bootstrap.update_environment(stackname)
    setdefault('.active-stack', stackname)
