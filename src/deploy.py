"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, deffile
import utils
from buildercore import core, bootstrap, cfngen, project

import logging

LOG = logging.getLogger(__name__)

def build_stack_name(pname, branch, cluster=None):
    "given a project and a branch, returns an instance name"
    stack_name = "%(pname)s--%(branch)s" % locals()
    if cluster:
        stack_name = stack_name + "--" + cluster
    return stack_name

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
def deploy(pname, branch=None, cluster=None):
    pdata = project.project_data(pname)
    branch_list = utils.git_remote_branches(pdata['repo'])
    branch_list = impose_ordering(branch_list)
    if not branch:
        branch = utils._pick('branch', branch_list, deffile('.branch'))
    stackname = build_stack_name(pname, branch, cluster)

    region = pdata['aws']['region']
    active_stacks = core.all_aws_stack_names(region)
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = {
            'instance_id': stackname,
            'branch': branch,
        }
        # tie branch names to alternate configurations
        if branch in project.project_alt_config_names(pdata):
            LOG.info("using alternate AWS configuration %r", branch)
            more_context['alt-config'] = branch
        cfngen.generate_stack(pname, **more_context)
        bootstrap.create_stack(stackname)
    bootstrap.update_stack(stackname)
    setdefault('.active-stack', stackname)
