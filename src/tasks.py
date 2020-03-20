"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be
better off in their own module. This module really is for stuff
that has no home."""
from buildercore import core, bootstrap, bakery
from utils import confirm, errcho
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
