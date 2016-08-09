import os
from buildercore import core, config, project, bakery
from buildercore.utils import lookup
from buildercore.decorators import osissue, osissuefn
import utils
from decorators import requires_aws_stack, debugtask, echo_output
import boto
from buildercore.core import boto_cfn_conn, boto_ec2_conn, connect_aws_with_stack, MultipleRegionsError
from fabric.api import settings, task
from fabric.contrib.console import confirm
from contextlib import contextmanager

import logging
LOG = logging.getLogger(__name__)

def find_region(stackname=None):
    """tries to find the region, but falls back to user input if there are multiple regions available.
    
    Uses stackname, if provided, to filter the available regions"""
    try:
        return core.find_region(stackname)
    except MultipleRegionsError as e:
        print "many possible regions found!"
        return utils._pick('region', e.regions())

def stack_list(region=None):
    "returns a list of realized stacks. does not include deleted stacks"
    if not region:
        region = find_region()
    return core.active_stack_names(region)

#
#
#

@task
@requires_aws_stack
def create_ami(stackname):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r. Continue?" % pname
    if not confirm(msg, default=False):
        print 'doing nothing'
        return
    amiid = bakery.create_ami(stackname)
    #amiid = "ami-e9ff3682"
    print 'AWS is now creating AMI with id', amiid
    path = pname + '.aws.ami'
    # wait until ami finished creating?
    #core.update_project_file(pname + ".aws.ami", amiid)
    new_project_file = project.update_project_file(path, amiid)
    output_file = project.write_project_file(new_project_file)
    print '\n' * 4
    print 'wrote', output_file
    print 'updated project file with new ami. these changes must be merged and committed manually'
    print '\n' * 4

#
#
#

@debugtask
@requires_aws_stack
@echo_output
def rds_snapshots(stackname):
    from boto import rds
    conn = rds.RDSConnection()
    instance = conn.get_all_dbinstances(instance_id=stackname)[0]
    # all snapshots order by creation time
    objdata = conn.get_all_dbsnapshots(instance_id=instance.id)
    data = sorted(map(lambda ss: ss.__dict__, objdata), key=lambda i: i['snapshot_create_time'])
    return data

@debugtask
@echo_output
def detailed_stack_list(project=None):
    region = find_region()
    results = core.active_aws_stacks(region, formatter=None)
    all_stacks = dict([(i.stack_name, vars(i)) for i in results])
    if project:
        return {k: v for k, v in all_stacks.items() if k.startswith("%s-" % project)}
    return all_stacks
