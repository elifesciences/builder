"""
trop.py is a module that uses the Troposphere library to build up 
a AWS Cloudformation (CFN) template dynamically, using values from 
the projects file and a bunch of sensible defaults.

It's job is to return the correct CFN JSON given a dictionary of 
data called a `context`.

`cfngen.py` is in charge of constructing this data struct and writing 
it to the correct file etc."""

from . import utils
from troposphere import GetAtt, Output, Ref, Template, ec2, rds, Base64, route53, Parameter
from functools import partial
import logging
from .decorators import osissue, osissuefn

LOG = logging.getLogger(__name__)

osissuefn("embarassing code. some of these constants should be pulled form project config or given better names.")

SECURITY_GROUP_TITLE = "StackSecurityGroup"
EC2_TITLE = 'EC2Instance'
RDS_TITLE = "AttachedDB"
RDS_SG_ID = "DBSecurityGroup"
DBSUBNETGROUP_TITLE = 'AttachedDBSubnet'
EXT_TITLE = "ExtraStorage"
EXT_MP_TITLE = "MountPoint"
R53_EXT_TITLE = "ExtDNS"
R53_EXT_HOSTED_ZONE = "elifesciences.org."
R53_INT_TITLE = "IntDNS"
R53_INT_HOSTED_ZONE = "elife.internal."

KEYPAIR = "KeyName"

def sg_rule(from_port, to_port=None, cidr_ip='0.0.0.0/0', ip_protocol='tcp'):
    if not to_port:
        to_port = from_port
    return ec2.SecurityGroupRule(**{
        # this is not a NAT port mapping like Vagrant! is a range of ports
        'FromPort': from_port,
        'ToPort': to_port,
        'IpProtocol': ip_protocol,
        'CidrIp': cidr_ip
    })

def security(context):
    default_cidr_ip = '0.0.0.0/0'
    default_protocol = 'tcp'
    ingress_ports = []
    for host_port, guest_port in context['project']['aws']['ports'].items():
        args = {'FromPort': host_port,
                'ToPort': guest_port,
                'IpProtocol': default_protocol,
                'CidrIp': default_cidr_ip}
        if isinstance(guest_port, dict):
            # complex value
            args['ToPort'] = guest_port['guest']
            args['CidrIp'] = guest_port.get('cidr-ip', default_cidr_ip)
            args['IpProtocol'] = guest_port.get('protocol', default_protocol)
        
        ingress_ports.append(ec2.SecurityGroupRule(**args))
    
    project_security = {
        "GroupDescription": "Enable SSH access via port 22",
        "VpcId": context['project']['aws']['vpc-id'],
        "SecurityGroupIngress": ingress_ports
    }
    return ec2.SecurityGroup(SECURITY_GROUP_TITLE, **project_security)

def instance_tags(context):
    return [
        ec2.Tag('Name', context['instance_id']),
        ec2.Tag('Owner', context['author']),
        ec2.Tag('Project', context['project_name']),
    ]

@osissue("deploy-user mention ties this to the shared-all strategy")
def ec2instance(context):
    lu = partial(utils.lu, context)
    project_ec2 = {
        "ImageId": lu('project.aws.ami'),
        "InstanceType": lu('project.aws.type'), # t2.small, m1.medium, etc
        "KeyName": Ref(KEYPAIR),
        "SecurityGroupIds": [Ref(SECURITY_GROUP_TITLE)],
        "SubnetId": lu('project.aws.subnet-id'), # ll: "subnet-1d4eb46a"
        "Tags": instance_tags(context),

        "UserData": Base64("""#!/bin/bash
echo %(build_vars)s > /etc/build-vars.json.b64""" % context),
    }
    return ec2.Instance(EC2_TITLE, **project_ec2)

def mkoutput(title, desc, val):
    if isinstance(val, tuple):
        val = GetAtt(val[0], val[1])
    return Output(title, Description=desc, Value=val)

def outputs():
    # http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html
    return [
        mkoutput("AZ", "Availability Zone of the newly created EC2 instance", ("EC2Instance", "AvailabilityZone")),
        mkoutput("InstanceId", "InstanceId of the newly created EC2 instance", Ref(EC2_TITLE)),

        # these values are generated by AWS
        mkoutput("PrivateIP", "Private IP address of the newly created EC2 instance", ("EC2Instance", "PrivateIp")),
        mkoutput("PublicIP", "Public IP address of the newly created EC2 instance", ("EC2Instance", "PublicIp")),
        mkoutput("PublicDNS", "Public DNSName of the newly created EC2 instance", ("EC2Instance", "PublicDnsName")),
        mkoutput("PrivateDNS", "Private DNSName of the newly created EC2 instance", ("EC2Instance", "PrivateDnsName")),
    ]

def rdsinstance(context):
    lu = partial(utils.lu, context)

    # db subnet
    rsn = rds.DBSubnetGroup(DBSUBNETGROUP_TITLE, **{
        "DBSubnetGroupDescription": "database subnet description here",
        "SubnetIds": lu('project.aws.rds.subnets'),
    })

    # rds security group. uses the ec2 security group
    rdssg = rds.DBSecurityGroup(RDS_SG_ID, **{
        "EC2VpcId": lu('project.aws.vpc-id'), # ll: vpc-78a2071d
        "DBSecurityGroupIngress": [
            {"EC2SecurityGroupId": GetAtt(SECURITY_GROUP_TITLE, "GroupId")},
        ],
        "GroupDescription": "RDS Security Group using an EC2 Security Group",
    })

    # db instance
    data = {
        'DBName': lu('rds_instance_id'), # dbname generated from instance id
        'DBInstanceIdentifier': lu('instance_id'), # ll: elife-lax--2015-12-31
        'PubliclyAccessible': False,
        'AllocatedStorage': lu('project.aws.rds.storage'),
        'StorageType': 'Standard',
        'MultiAZ': lu('project.aws.rds.multi-az'),
        "DBSecurityGroups": [Ref(rdssg)],
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
    return rsn, rdbi, rdssg

def ext_volume(context):
    lu = partial(utils.lu, context)
    vtype = lu('project.ext.type', default='standard')
    # who cares what gp2 stands for? everyone knows what 'ssd' and 'standard' mean ...
    if vtype == 'ssd':
        vtype = 'gp2'
    
    args = {
        "Size": str(lu('project.aws.ext.size')),
        "AvailabilityZone": GetAtt(EC2_TITLE, "AvailabilityZone"),
        "VolumeType": vtype,
    }
    ec2v = ec2.Volume(EXT_TITLE, **args)
    
    args = {
        "InstanceId": Ref(EC2_TITLE),
        "VolumeId": Ref(ec2v),
        "Device": lu('project.aws.ext.device'),
    }
    ec2va = ec2.VolumeAttachment(EXT_MP_TITLE, **args)
    return ec2v, ec2va

def external_dns(context):
    hostedzone = R53_EXT_HOSTED_ZONE # The DNS name of an existing Amazon Route 53 hosted zone    
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        #Comment = "DNS name for my instance.",
        Name = context['hostname'] + "." + hostedzone,
        Type = "A",
        TTL = "900",
        ResourceRecords=[GetAtt(EC2_TITLE, "PublicIp")],
    )
    return dns_record

def internal_dns(context):
    hostedzone = R53_INT_HOSTED_ZONE # The DNS name of an existing Amazon Route 53 hosted zone    
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        #Comment = "DNS name for my instance.",
        Name = context['hostname'] + "." + hostedzone,
        Type = "A",
        TTL = "900",
        ResourceRecords=[GetAtt(EC2_TITLE, "PrivateIp")],
    )
    return dns_record
    

def render(context):
    secgroup = security(context)
    instance = ec2instance(context)

    template = Template()
    template.add_resource(secgroup)
    template.add_resource(instance)

    keyname = template.add_parameter(Parameter(KEYPAIR, **{
        "Type": "String",
        "Description": "EC2 KeyPair that enables SSH access to this instance",
    }))
    
    cfn_outputs = outputs()

    if context['project']['aws'].has_key('rds'):
        map(template.add_resource, rdsinstance(context))
        cfn_outputs.extend([
            mkoutput("RDSHost", "Connection endpoint for the DB cluster", (RDS_TITLE, "Endpoint.Address")),
            mkoutput("RDSPort", "The port number on which the database accepts connections", (RDS_TITLE, "Endpoint.Port")),])
    
    if context['project']['aws'].has_key('ext'):
        map(template.add_resource, ext_volume(context))

    if context['hostname']: # None if one couldn't be generated
        template.add_resource(external_dns(context))
        template.add_resource(internal_dns(context))        
        cfn_outputs.extend([
            mkoutput("DomainName", "Domain name of the newly created EC2 instance", Ref(R53_EXT_TITLE)),
            mkoutput("IntDomainName", "Domain name of the newly created EC2 instance", Ref(R53_INT_TITLE))])

    map(template.add_output, cfn_outputs)
    return template.to_json()
