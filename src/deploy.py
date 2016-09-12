"""module concerns itself with tasks involving branch deployments of projects."""

from fabric.api import task
from decorators import requires_branch_deployable_project, echo_output, setdefault, deffile, requires_aws_stack
import utils
from buildercore import core, bootstrap, cfngen, project
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
def deploy(pname, instance_id=None, branch='master'):
    pdata = project.project_data(pname)
    if not branch:
        branch_list = utils.git_remote_branches(pdata['repo'])
        branch_list = impose_ordering(branch_list)
        branch = utils._pick('branch', branch_list, deffile('.branch'))
    stackname = core.mk_stackname(pname, instance_id)

    region = pdata['aws']['region']
    active_stacks = core.active_stack_names(region)
    if stackname in active_stacks:
        LOG.info("stack %r exists, skipping creation", stackname)
    else:
        LOG.info("stack %r doesn't exist, creating", stackname)
        more_context = {
            'stackname': stackname,
            'branch': branch,
        }
        # optionally select alternate configurations if it matches the instance name
        if instance_id in project.project_alt_config_names(pdata):
            LOG.info("using alternate AWS configuration %r", instance_id)
            more_context['alt-config'] = instance_id
        cfngen.generate_stack(pname, **more_context)

    bootstrap.create_update(stackname)        
    setdefault('.active-stack', stackname)

@task(name='switch_revision_update_instance')
@requires_aws_stack
def switch_revision_update_instance(stackname, revision=None):
    buildvars.switch_revision(stackname, revision)
    with core.stack_conn(stackname):
        return bootstrap.run_script('highstate.sh')
