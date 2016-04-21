import boto3
import utils
from utils import has_expired, when_expires
import logging
from decorators import echo_output, admintask

LOG = logging.getLogger(__name__)

@admintask
@echo_output
def stack_list():
    import aws
    stacks = aws.stack_list()
    data = {
        'stacks': stacks,
        'num': len(stacks)
    }
    return data
    








#
#
#

def cfnconn():
    return boto3.client("cloudformation")

def ec2conn():
    return boto3.client("ec2")

def all_stacks():
    return cfnconn().describe_stacks()

def stack(stackname):
    return cfnconn().describe_stacks(StackName=stackname)

def stack_resources(stackname):
    "returns a summary of resources in this stack"
    try:
        _resource_summary = cfnconn().describe_stack_resources(StackName=stackname)
        _resource_details = map(resource_details, _resource_summary['StackResources'])
        return {resource['ResourceType']: resource for resource in _resource_details}
    except Exception, ex:
        LOG.exception(ex)
        return {}

@utils.cached
def cached_stack_resources(stackname):
    print 'CACHE MISS. cached stack resources'
    return stack_resources(stackname)

def _wrangle_ec2(ec2_detail):
    "takes beautifully structured and organised data and mutilates it for our convenience"
    meat = ec2_detail['Reservations'][0]['Instances'][0]
    meat['Tags'] = {p['Key']:p['Value'] for p in meat['Tags']}

    # convenience values here. so much easier than further downstream
    meat['has_expired'] = has_expired(meat['Tags'].get('Expires'))
    meat['is_auto'] = meat['Tags'].get('CreationType', 'manual') == 'auto'
    meat['no_expiry_date'] = not meat['Tags'].has_key('Expires')

    exp_delta = when_expires(meat['Tags'].get('Expires'))
    meat['time_to_expiry'] = exp_delta
    meat['expiry_days'] = getattr(exp_delta, 'days', None)

    return meat

def ec2_details(resource):
    "detailed information about an ec2 instance"
    instance_id = resource['PhysicalResourceId']
    # raw data is far more structured that we need it.
    data = ec2conn().describe_instances(InstanceIds=[instance_id])
    return _wrangle_ec2(data)

def security_group_details(resource):
    rid = resource['PhysicalResourceId']
    data = ec2conn().describe_security_groups(GroupIds=[rid])
    return data['SecurityGroups']

def resource_details(resource):
    "returns details of the given resource."
    handlers = {
        'AWS::EC2::Instance': ec2_details,
        'AWS::EC2::SecurityGroup': security_group_details,
    }
    resource_type = resource['ResourceType']
    ret = resource
    if handlers.has_key(resource_type):
        try:
            ret['detail'] = handlers[resource_type](resource)
        except Exception, ex:
            LOG.exception(ex)
            ret['detail'] = {'error': ex.message, 'exception': ex}
    return ret
