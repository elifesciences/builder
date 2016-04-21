import os
from fabric.api import settings
from fabfile import PROJECT_DIR
from buildercore import core, config
import utils
import boto
from contextlib import contextmanager

import logging
LOG = logging.getLogger(__name__)

#
# perhaps these should live in their own file?
#


def boto_cfn_conn():
    #return boto.cloudformation.connect_to_region('us-west-2')
    return boto.connect_cloudformation()

def boto_ec2_conn():
    return boto.connect_ec2()

def get_instance(iid):
    ec2 = boto_ec2_conn()
    return ec2.get_only_instances([iid])[0]

def deploy_user_pem():
    return os.path.join(PROJECT_DIR, 'payload/deploy-user.pem')

def stack_list():
    "returns a list of realized stacks. does not include deleted stacks"
    return core.all_aws_stack_names()

def describe_stack(stackname):
    data = utils.just_one(boto_cfn_conn().describe_stacks(stackname)).__dict__
    if data.has_key('outputs'):
        data['indexed_output'] = {row.key: row.value for row in data['outputs']}
    try:
        # TODO: is there someway to go straight to the instance ID ?
        # a CloudFormation's outputs go stale! because we can't trust the data it
        # gives us, we sometimes take it's instance-id and talk to the instance directly.
        inst_id = data['indexed_output']['InstanceId']
        inst = get_instance(inst_id)
        data['instance'] = inst.__dict__
    except Exception:
        LOG.exception('caught an exception attempting to discover more information about this instance. The instance may not exist yet ...')
    return data

@contextmanager
def stack_conn(stackname, username=config.DEPLOY_USER):
    public_ip = describe_stack(stackname)['instance']['ip_address']
    with settings(user=username, host_string=public_ip, key_filename=deploy_user_pem()):
        yield
