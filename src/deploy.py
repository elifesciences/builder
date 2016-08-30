"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, deffile
import utils
from buildercore import core, bootstrap, cfngen, project

import logging

LOG = logging.getLogger(__name__)

def build_stack_name(pname, cluster):
    "given a project and a cluster, returns an instance name"
    return "%(pname)s--%(cluster)s" % locals()

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
def deploy(pname, cluster=None, branch='master'):
    pdata = project.project_data(pname)
    if not branch:
        branch_list = utils.git_remote_branches(pdata['repo'])
        branch_list = impose_ordering(branch_list)
        branch = utils._pick('branch', branch_list, deffile('.branch'))
    stackname = build_stack_name(pname, cluster)

    region = pdata['aws']['region']
    active_stacks = core.active_stack_names(region)
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = {
            'instance_id': stackname,
            'branch': branch,
            'cluster': cluster,
        }
        # optionally select alternate configurations if it matches the cluster name
        if cluster in project.project_alt_config_names(pdata):
            LOG.info("using alternate AWS configuration %r", cluster)
            more_context['alt-config'] = cluster
        cfngen.generate_stack(pname, **more_context)
        bootstrap.create_stack(stackname)
    bootstrap.update_stack(stackname)
    setdefault('.active-stack', stackname)
