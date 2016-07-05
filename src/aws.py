import os
from buildercore import core, config, project
from buildercore.utils import lookup
from buildercore.decorators import osissue, osissuefn
import utils
from decorators import requires_aws_stack, debugtask, echo_output
import boto
from buildercore.core import boto_cfn_conn, boto_ec2_conn, connect_aws_with_stack
from fabric.api import settings, task
from contextlib import contextmanager

import logging
LOG = logging.getLogger(__name__)

def find_region(stackname=None):
    """used when we haven't got a stack and need to know about stacks in a particular region.
    if a stack is provided, it uses the one provided in it's configuration.
    otherwise, generates a list of used regions from project data

    if more than one region available, it will raise an EnvironmentError.
    until we have some means of supporting multiple regions, this is the best solution"""
    region = None
    if stackname:
        pdata = core.project_data_for_stackname(stackname)
        return pdata['aws']['region']

    all_projects = project.project_map()
    all_regions = [lookup(p, 'aws.region', None) for p in all_projects.values()]
    region_list = list(set(filter(None, all_regions))) # remove any Nones, make unique, make a list
    if not region_list:
        raise EnvironmentError("no regions available at all!")
    if len(region_list) > 1:
        if True:
            print "many possible regions found!"
            return utils._pick(region, region_list)        
        raise EnvironmentError("multiple regions available but not yet supported!: %s" % region_list)
    return region_list[0]

def stack_list(region=None):
    "returns a list of realized stacks. does not include deleted stacks"
    if not region:
        region = find_region()
    return core.all_aws_stack_names(region)

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
