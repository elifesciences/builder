"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be
better off in their own module. This module really is for stuff
that has no home."""
from buildercore import core, bootstrap
from fabric.api import local, task
from utils import confirm, errcho
from decorators import requires_aws_stack, debugtask
from buildercore import bakery
from buildercore.core import stack_conn
from buildercore.context_handler import load_context

@task
@requires_aws_stack
def create_ami(stackname, name=None):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r" % pname
    confirm(msg)

    amiid = bakery.create_ami(stackname, name)
    errcho('AWS has created AMI with id:')
    print(amiid)
    errcho('update project file with new ami %s. these changes must be merged and committed manually' % amiid)

#
#
#

@debugtask
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

@task
@requires_aws_stack
def repair_cfn_info(stackname):
    with stack_conn(stackname):
        bootstrap.write_environment_info(stackname, overwrite=True)

@task
@requires_aws_stack
def repair_context(stackname):
    # triggers the workaround of downloading it from EC2 and persisting it
    load_context(stackname)

@task
@requires_aws_stack
def remove_minion_key(stackname):
    bootstrap.remove_minion_key(stackname)
