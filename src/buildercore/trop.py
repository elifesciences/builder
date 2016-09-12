"""
trop.py is a module that uses the Troposphere library to build up 
a AWS Cloudformation (CFN) template dynamically, using values from 
the projects file and a bunch of sensible defaults.

It's job is to return the correct CFN JSON given a dictionary of 
data called a `context`.

`cfngen.py` is in charge of constructing this data struct and writing 
it to the correct file etc."""

import base64
import json
import re
from . import utils
from troposphere import GetAtt, Output, Ref, Template, ec2, rds, sns, sqs, Base64, route53, Parameter

from functools import partial
import logging
from .decorators import osissuefn
from .utils import first

LOG = logging.getLogger(__name__)

osissuefn("embarassing code. some of these constants should be pulled form project config or given better names.")

SECURITY_GROUP_TITLE = "StackSecurityGroup"
EC2_TITLE = 'EC2Instance%d'
RDS_TITLE = "AttachedDB"
RDS_SG_ID = "DBSecurityGroup"
DBSUBNETGROUP_TITLE = 'AttachedDBSubnet'
EXT_TITLE = "ExtraStorage"
EXT_MP_TITLE = "MountPoint"
R53_EXT_TITLE = "ExtDNS"
R53_INT_TITLE = "IntDNS"

KEYPAIR = "KeyName"

def ingress(port, end_port=None, protocol='tcp', cidr='0.0.0.0/0'):
    if not end_port:
        end_port = port
    return ec2.SecurityGroupRule(**{
        'FromPort': port,
        'ToPort': end_port,
        'IpProtocol': protocol,
        'CidrIp': cidr
    })

def complex_ingress(struct):
    # it's just not that simple
    if not isinstance(struct, dict):
        port = struct
        return ingress(port)
    assert len(struct.items()) == 1, "port mapping struct must contain a single key: %r" % struct
    port, struct = first(struct.items())
    default_end_port = port
    default_cidr_ip = '0.0.0.0/0'
    default_protocol = 'tcp'
    return ingress(port, **{
        # TODO: rename 'guest' in project file to something less wrong
        'end_port': struct.get('guest', default_end_port),
        'protocol': struct.get('protocol', default_protocol),
        'cidr': struct.get('cidr-ip', default_cidr_ip),
    })

def security_group(group_id, vpc_id, ingress_structs, description=""):
    return ec2.SecurityGroup(group_id, **{
        'GroupDescription': description or 'security group',
        'VpcId': vpc_id,
        'SecurityGroupIngress': map(complex_ingress, ingress_structs)
    })

def ec2_security(context):
    assert 'ports' in context['project']['aws'], "Missing `ports` configuration in `aws` for '%s'" % context['stackname']

    return security_group(
        SECURITY_GROUP_TITLE,
        context['project']['aws']['vpc-id'],
        context['project']['aws']['ports']
    ) # list of strings or dicts

def rds_security(context):
    "returns a security group for the rds instance. this security group only allows access within the subnet"
    engine_ports = {
        'postgres': 5432,
        'mysql': 3306
    }
    ingress_ports = [engine_ports[context['project']['aws']['rds']['engine']]]
    return security_group("VPCSecurityGroup", \
       context['project']['aws']['vpc-id'], \
       ingress_ports, \
       "RDS DB security group")

#
#
#


def instance_tags(context, node=None):
    tags = [
        ec2.Tag('Owner', context['author']),
        # hierarchically ordered
        ec2.Tag('Project', context['project_name']),
        ec2.Tag('Cluster', context['stackname']),
    ]
    if node:
        tags.append(ec2.Tag('Name', '%s--%d' % (context['stackname'], node)))
        tags.append(ec2.Tag('Node', '%s' % node))
    else:
        tags.append(ec2.Tag('Name', context['stackname']))
    return tags

def ec2instance(context, node):
    lu = partial(utils.lu, context)
    build_vars = dict(context)
    build_vars['node'] = node
    build_vars['nodename'] = "%s--%s" % (context['stackname'], node)
    # the above context will reside on the server at /etc/build-vars.json.b64
    # this gives Salt all (most) of the data that was available at template compile time.
    build_vars_serialization = base64.b64encode(json.dumps(build_vars))

    project_ec2 = {
        "ImageId": lu('project.aws.ami'),
        "InstanceType": lu('project.aws.type'), # t2.small, m1.medium, etc
        "KeyName": Ref(KEYPAIR),
        "SecurityGroupIds": [Ref(SECURITY_GROUP_TITLE)],
        "SubnetId": lu('project.aws.subnet-id'), # ll: "subnet-1d4eb46a"
        "Tags": instance_tags(context, node),

        "UserData": Base64("""#!/bin/bash
echo %s > /etc/build-vars.json.b64""" % build_vars_serialization),
    }
    return ec2.Instance(EC2_TITLE % node, **project_ec2)

def mkoutput(title, desc, val):
    if isinstance(val, tuple):
        val = GetAtt(val[0], val[1])
    return Output(title, Description=desc, Value=val)

def _ec2_outputs(node):
    # http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html
    return [
        mkoutput("AZ%d" % node, "Availability Zone of the newly created EC2 instance", (EC2_TITLE % node, "AvailabilityZone")),
        mkoutput("InstanceId%d" % node, "InstanceId of the newly created EC2 instance", Ref(EC2_TITLE % node)),

        # these values are generated by AWS
        mkoutput("PrivateIP%d" % node, "Private IP address of the newly created EC2 instance", (EC2_TITLE % node, "PrivateIp")),
        mkoutput("PublicIP%d" % node, "Public IP address of the newly created EC2 instance", (EC2_TITLE % node, "PublicIp")),
        mkoutput("PublicDNS%d" % node, "Public DNSName of the newly created EC2 instance", (EC2_TITLE % node, "PublicDnsName")),
        mkoutput("PrivateDNS%d" % node, "Private DNSName of the newly created EC2 instance", (EC2_TITLE % node, "PrivateDnsName")),
    ]

def rdsinstance(context):
    lu = partial(utils.lu, context)

    # db subnet *group*
    # it's expected the db subnets themselves are already created within the VPC
    # you just need to plug their ids into the project file.
    # not really sure if a subnet group is anything more meaningful than 'a collection of subnet ids'
    rsn = rds.DBSubnetGroup(DBSUBNETGROUP_TITLE, **{
        "DBSubnetGroupDescription": "a group of subnets for this rds instance.",
        "SubnetIds": lu('project.aws.rds.subnets'),
    })

    # rds security group. uses the ec2 security group
    vpcdbsg = rds_security(context)

    # db instance
    data = {
        'DBName': lu('rds_dbname'), # dbname generated from instance id.
        'DBInstanceIdentifier': lu('rds_instance_id'), # ll: 'lax-2015-12-31' from 'lax--2015-12-31'
        'PubliclyAccessible': False,
        'AllocatedStorage': lu('project.aws.rds.storage'),
        'StorageType': 'Standard',
        'MultiAZ': lu('project.aws.rds.multi-az'),
        'VPCSecurityGroups': [Ref(vpcdbsg)],
        'DBSubnetGroupName': Ref(rsn),
        'DBInstanceClass': lu('project.aws.rds.type'),
        'Engine': lu('project.aws.rds.engine'),
        'MasterUsername': lu('rds_username'), # pillar data is now UNavailable
        'MasterUserPassword': lu('rds_password'),
        'BackupRetentionPeriod': lu('project.aws.rds.backup-retention'),
        'DeletionPolicy': 'Snapshot',
        "Tags": instance_tags(context),
        "AllowMajorVersionUpgrade": False, # default? not specified.
        "AutoMinorVersionUpgrade": True, # default
        # something is converting this value to an int :(
        "EngineVersion": str(lu('project.aws.rds.version')), # 'defaults.aws.rds.storage')),
    }
    rdbi = rds.DBInstance(RDS_TITLE, **data)
    return rsn, rdbi, vpcdbsg

def ext_volume(context_ext):
    vtype = context_ext.get('type', 'standard')
    # who cares what gp2 stands for? everyone knows what 'ssd' and 'standard' mean ...
    if vtype == 'ssd':
        vtype = 'gp2'
    
    args = {
        "Size": str(context_ext['size']),
        "AvailabilityZone": GetAtt(EC2_TITLE, "AvailabilityZone"),
        "VolumeType": vtype,
    }
    ec2v = ec2.Volume(EXT_TITLE, **args)
    
    args = {
        "InstanceId": Ref(EC2_TITLE),
        "VolumeId": Ref(ec2v),
        "Device": context_ext['device'],
    }
    ec2va = ec2.VolumeAttachment(EXT_MP_TITLE, **args)
    return ec2v, ec2va

def external_dns(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        Comment = "External DNS record",
        Name = context['full_hostname'],
        Type = "A",
        TTL = "900",
        ResourceRecords=[GetAtt(EC2_TITLE, "PublicIp")],
    )
    return dns_record

def internal_dns(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['int_domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        Comment = "Internal DNS record",
        Name = context['int_full_hostname'],
        Type = "A",
        TTL = "900",
        ResourceRecords=[GetAtt(EC2_TITLE, "PrivateIp")],
    )
    return dns_record
    

def render(context):
    template = Template()
    cfn_outputs = []

    if context['ec2']:
        secgroup = ec2_security(context)
        template.add_resource(secgroup)

        for node in range(1, context['ec2']['cluster-size'] + 1):
            instance = ec2instance(context, node)
            template.add_resource(instance)
            cfn_outputs.extend(_ec2_outputs(node))

        template.add_parameter(Parameter(KEYPAIR, **{
            "Type": "String",
            "Description": "EC2 KeyPair that enables SSH access to this instance",
        }))

    if context['rds_instance_id']:
        map(template.add_resource, rdsinstance(context))
        cfn_outputs.extend([
            mkoutput("RDSHost", "Connection endpoint for the DB cluster", (RDS_TITLE, "Endpoint.Address")),
            mkoutput("RDSPort", "The port number on which the database accepts connections", (RDS_TITLE, "Endpoint.Port")),])
    
    if context['ext']:
        map(template.add_resource, ext_volume(context['ext']))

    for topic_name in context['sns']:
        topic = template.add_resource(sns.Topic(
            _sanitize_title(topic_name) + "Topic",
            TopicName=topic_name
        ))
        template.add_output(Output(
            _sanitize_title(topic_name) + "TopicArn",
            Value=Ref(topic)
        ))

    for queue_name in context['sqs']:
        queue = template.add_resource(sqs.Queue(
            _sanitize_title(queue_name) + "Queue", 
            QueueName=queue_name
        ))
        template.add_output(Output(
            _sanitize_title(queue_name) + "QueueArn",
            Value=GetAtt(queue, "Arn")
        ))

    # TODO: these hostnames will be assigned to an ELB for cluster-size >= 2
    if context['ec2']['cluster-size'] == 1:
        if context['full_hostname']:
            template.add_resource(external_dns(context))
            cfn_outputs.extend([
                mkoutput("DomainName", "Domain name of the newly created EC2 instance", Ref(R53_EXT_TITLE)),
            ])

        if context['int_full_hostname']:
            template.add_resource(internal_dns(context))        
            cfn_outputs.extend([
                mkoutput("IntDomainName", "Domain name of the newly created EC2 instance", Ref(R53_INT_TITLE))
            ])

    map(template.add_output, cfn_outputs)
    return template.to_json()

def _sanitize_title(string):
    return "".join(map(str.capitalize, string.split("-")))
