import os
from fabric.api import settings
from fabfile import PROJECT_DIR
from buildercore import core, config, project
from buildercore.utils import lookup
from buildercore.decorators import osissue, osissuefn
import utils
import boto
from contextlib import contextmanager

import logging
LOG = logging.getLogger(__name__)

#
# perhaps these should live in their own file?
#

from buildercore.core import boto_cfn_conn, boto_ec2_conn, connect_aws_with_stack

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
