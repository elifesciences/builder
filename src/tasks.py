"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be
better off in their own module. This module really is for stuff
that has no home."""
import logging

import report
from buildercore import bakery, core
from buildercore.context_handler import load_context
from buildercore.core import stack_conn
from decorators import requires_aws_stack
from utils import confirm, errcho

LOG = logging.getLogger(__name__)

@requires_aws_stack
def create_ami(stackname, name=None):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r" % pname
    confirm(msg)

    amiid = bakery.create_ami(stackname, name)
    print(amiid)
    errcho('update project file with new ami %s. these changes must be merged and committed manually' % amiid)

def delete_ami(image_id, image_name=None):
    # deleting ami-0d704606bde72ad4c ('containers-20190325114149')
    msg = "deleting %s (%r)" % (image_id, image_name)
    if not image_name:
        msg = "deleting %s" % image_id
    errcho(msg)
    bakery.delete_ami(image_id)

def delete_all_amis_to_prune():
    image_list = report.all_amis_to_prune()
    msg = "%s AMIs to delete" % len(image_list)
    if not image_list:
        errcho(msg)
        return
    confirm(msg)
    [delete_ami(image['ImageId'], image['Name']) for image in image_list]

@requires_aws_stack
def repair_cfn_info(stackname):
    """refreshes remote `/etc/cfn-info.json`
    this file is a simple map of Cloudformation data stored on the ec2 instance.
    it may contain information about domain names, RDS, managed Redis instances, etc."""
    with stack_conn(stackname):
        core.write_environment_info(stackname, overwrite=True)

@requires_aws_stack
def repair_context(stackname):
    """refreshes local stack context data.
    the context is a simple map of data about a stack stored in S3."""
    load_context(stackname)

@requires_aws_stack
def remove_minion_key(stackname):
    "deletes a salt minion's unique key from the salt master."
    core.remove_minion_key(stackname)
