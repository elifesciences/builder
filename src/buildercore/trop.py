"""
trop.py is a module that uses the Troposphere library to build up
a AWS Cloudformation (CFN) template dynamically, using values from
the projects file and a bunch of sensible defaults.

It's job is to return the correct CFN JSON given a dictionary of
data called a `context`.

`cfngen.py` is in charge of constructing this data struct and writing
it to the correct file etc."""

from . import utils, bvars
from troposphere import GetAtt, Output, Ref, Template, ec2, rds, sns, sqs, Base64, route53, Parameter
from troposphere import s3, cloudfront, elasticloadbalancing as elb

from functools import partial
import logging
from .utils import first, ensure

LOG = logging.getLogger(__name__)

# TODO: embarassing code. some of these constants should be pulled form project config or given better names.

SECURITY_GROUP_TITLE = "StackSecurityGroup"
SECURITY_GROUP_ELB_TITLE = "ELBSecurityGroup"
EC2_TITLE = 'EC2Instance1'
EC2_TITLE_NODE = 'EC2Instance%d'
ELB_TITLE = 'ElasticLoadBalancer'
RDS_TITLE = "AttachedDB"
RDS_SG_ID = "DBSecurityGroup"
DBSUBNETGROUP_TITLE = 'AttachedDBSubnet'
EXT_TITLE = "ExtraStorage"
EXT_MP_TITLE = "MountPoint"
R53_EXT_TITLE = "ExtDNS"
R53_INT_TITLE = "IntDNS"
R53_CDN_TITLE = "CloudFrontCDNDNS%s"
CLOUDFRONT_TITLE = 'CloudFrontCDN'

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
    ensure('ports' in context['project']['aws'],
           "Missing `ports` configuration in `aws` for '%s'" % context['stackname'])

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
    ingress_ports = [engine_ports[context['project']['aws']['rds']['engine'].lower()]]
    return security_group("VPCSecurityGroup",
                          context['project']['aws']['vpc-id'],
                          ingress_ports,
                          "RDS DB security group")

#
#
#


def _generic_tags(context):
    return {
        'Owner': context['author'],
        'Project': context['project_name'], # journal
        'Environment': context['instance_id'], # stack instance id
        # the name AWS Console uses to label an instance
        'Name': context['stackname'] # ll: journal-prod
    }

def instance_tags(context, node=None):
    # NOTE: RDS instances also call this function
    tags = _generic_tags(context)
    if node:
        # this instance is part of a cluster
        tags.update({
            'Name': '%s--%d' % (context['stackname'], node), # ll: journal--prod--1
            'Cluster': context['stackname'], # ll: journal--prod
            'Node': node, # ll: 1
        })
    return [ec2.Tag(key, str(value)) for key, value in tags.items()]

def elb_tags(context):
    tags = _generic_tags(context)
    tags.update({
        'Name': '%s--elb' % context['stackname'], # ll: journal--prod--elb
        'Cluster': context['stackname'], # ll: journal--prod
    })
    return [ec2.Tag(key, value) for key, value in tags.items()]

def mkoutput(title, desc, val):
    if isinstance(val, tuple):
        val = GetAtt(val[0], val[1])
    return Output(title, Description=desc, Value=val)

#
#
#

def build_vars(context, node):
    buildvars = dict(context)
    del buildvars['project']
    buildvars['node'] = node
    buildvars['nodename'] = "%s--%s" % (context['stackname'], node)
    # the above context will reside on the server at /etc/build-vars.json.b64
    # this gives Salt all (most) of the data that was available at template compile time.
    return buildvars

def ec2instance(context, node):
    lu = partial(utils.lu, context)
    buildvars = build_vars(context, node)
    buildvars_serialization = bvars.encode_bvars(buildvars)

    odd = node % 2 == 1
    if odd:
        subnet_id = lu('project.aws.subnet-id')
    else:
        subnet_id = lu('project.aws.redundant-subnet-id')

    project_ec2 = {
        "ImageId": lu('project.aws.ec2.ami'),
        "InstanceType": lu('project.aws.type'), # t2.small, m1.medium, etc
        "KeyName": Ref(KEYPAIR),
        "SecurityGroupIds": [Ref(SECURITY_GROUP_TITLE)],
        "SubnetId": subnet_id, # ll: "subnet-1d4eb46a"
        "Tags": instance_tags(context, node),

        "UserData": Base64("""#!/bin/bash
echo %s > /etc/build-vars.json.b64""" % buildvars_serialization),
    }
    return ec2.Instance(EC2_TITLE_NODE % node, **project_ec2)

def rdsinstance(context, template):
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
    map(template.add_resource, [rsn, rdbi, vpcdbsg])

    outputs = [
        mkoutput("RDSHost", "Connection endpoint for the DB cluster", (RDS_TITLE, "Endpoint.Address")),
        mkoutput("RDSPort", "The port number on which the database accepts connections", (RDS_TITLE, "Endpoint.Port")),
    ]
    map(template.add_output, outputs)

def ext_volume(context, template):
    context_ext = context['ext']
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
    map(template.add_resource, [ec2v, ec2va])

def external_dns_ec2(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        Comment="External DNS record for EC2",
        Name=context['full_hostname'],
        Type="A",
        TTL="60",
        ResourceRecords=[GetAtt(EC2_TITLE, "PublicIp")],
    )
    return dns_record

def internal_dns(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['int_domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        Comment="Internal DNS record for EC2",
        Name=context['int_full_hostname'],
        Type="A",
        TTL="60",
        ResourceRecords=[GetAtt(EC2_TITLE, "PrivateIp")],
    )
    return dns_record

# TODO: remove duplication, but also unify with PR #46
def external_dns_elb(context):
    # http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        Comment="External DNS record for ELB",
        Name=context['full_hostname'],
        Type="A",
        AliasTarget=route53.AliasTarget(
            GetAtt(ELB_TITLE, "CanonicalHostedZoneNameID"),
            GetAtt(ELB_TITLE, "DNSName")
        )
    )
    return dns_record

def internal_dns_elb(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['int_domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        Comment="Internal DNS record for ELB",
        Name=context['int_full_hostname'],
        Type="A",
        AliasTarget=route53.AliasTarget(
            GetAtt(ELB_TITLE, "CanonicalHostedZoneNameID"),
            GetAtt(ELB_TITLE, "DNSName")
        )
    )
    return dns_record

def external_dns_cloudfront(context):
    # http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html
    dns_records = []
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    i = 1
    for subdomain in context['cloudfront']['subdomains']:
        cdn_hostname = "%s.%s" % (subdomain, context['domain'])
        dns_records.append(route53.RecordSetType(
            R53_CDN_TITLE % i,
            HostedZoneName=hostedzone,
            Comment="External DNS record for Cloudfront distribution",
            Name=cdn_hostname,
            Type="A",
            AliasTarget=route53.AliasTarget(
                # Magic value, put in a constant
                "Z2FDTNDATAQYW2",
                GetAtt(CLOUDFRONT_TITLE, "DomainName")
            )
        ))
        i = i + 1
    return dns_records

#
# render_* funcs
#

def _sanitize_title(string):
    return "".join(map(str.capitalize, string.split("-")))

def render_ec2(context, template):
    # all ec2 nodes in a cluster share the same security group
    secgroup = ec2_security(context)
    template.add_resource(secgroup)

    ec2_instances = []
    for node in range(1, context['ec2']['cluster-size'] + 1):
        instance = ec2instance(context, node)
        ec2_instances.append(instance)
        template.add_resource(instance)

        outputs = [
            mkoutput("AZ%d" % node, "Availability Zone of the newly created EC2 instance", (EC2_TITLE_NODE % node, "AvailabilityZone")),
            mkoutput("InstanceId%d" % node, "InstanceId of the newly created EC2 instance", Ref(EC2_TITLE_NODE % node)),
            mkoutput("PrivateIP%d" % node, "Private IP address of the newly created EC2 instance", (EC2_TITLE_NODE % node, "PrivateIp")),
            mkoutput("PublicIP%d" % node, "Public IP address of the newly created EC2 instance", (EC2_TITLE_NODE % node, "PublicIp")),
        ]
        map(template.add_output, outputs)

    # all ec2 nodes in a cluster share the same keypair
    template.add_parameter(Parameter(KEYPAIR, **{
        "Type": "String",
        "Description": "EC2 KeyPair that enables SSH access to this instance",
    }))
    return ec2_instances

def render_sns(context, template):
    for topic_name in context['sns']:
        topic = template.add_resource(sns.Topic(
            _sanitize_title(topic_name) + "Topic",
            TopicName=topic_name
        ))
        template.add_output(Output(
            _sanitize_title(topic_name) + "TopicArn",
            Value=Ref(topic)
        ))

def render_sqs(context, template):
    for queue_name in context['sqs']:
        queue = template.add_resource(sqs.Queue(
            _sanitize_title(queue_name) + "Queue",
            QueueName=queue_name
        ))
        template.add_output(Output(
            _sanitize_title(queue_name) + "QueueArn",
            Value=GetAtt(queue, "Arn")
        ))

def render_s3(context, template):
    for bucket_name in context['s3']:
        props = {
            'DeletionPolicy': context['s3'][bucket_name]['deletion-policy'].capitalize()
        }
        bucket_title = _sanitize_title(bucket_name) + "Bucket"
        if context['s3'][bucket_name]['cors']:
            # generic configuration for allowing read-only access
            props['CorsConfiguration'] = s3.CorsConfiguration(
                CorsRules=[
                    s3.CorsRules(
                        AllowedHeaders=['*'],
                        AllowedMethods=['GET', 'HEAD'],
                        AllowedOrigins=['*']
                    )
                ]
            )
        if context['s3'][bucket_name]['website-configuration']:
            index_document = context['s3'][bucket_name]['website-configuration'].get('index-document', 'index.html')
            props['WebsiteConfiguration'] = s3.WebsiteConfiguration(
                IndexDocument=index_document
            )
            template.add_resource(s3.BucketPolicy(
                "%sPolicy" % bucket_title,
                Bucket=bucket_name,
                PolicyDocument={
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Sid": "AddPerm",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["s3:GetObject"],
                        "Resource":[
                            "arn:aws:s3:::%s/*" % bucket_name
                        ]
                    }]
                }
            ))
        template.add_resource(s3.Bucket(
            bucket_title,
            BucketName=bucket_name,
            **props
        ))

def render_elb(context, template, ec2_instances):
    ensure(any([context['full_hostname'], context['int_full_hostname']]),
           "An ELB must have either an external or an internal DNS entry")

    elb_is_public = True if context['full_hostname'] else False
    listeners_policy_names = []

    if context['elb']['stickiness']:
        cookie_stickiness = [elb.LBCookieStickinessPolicy(
            PolicyName="BrowserSessionLongCookieStickinessPolicy"
        )]
        listeners_policy_names.append('BrowserSessionLongCookieStickinessPolicy')
    else:
        cookie_stickiness = []

    if isinstance(context['elb']['protocol'], str):
        protocols = [context['elb']['protocol']]
    else:
        protocols = context['elb']['protocol']

    listeners = []
    elb_ports = []
    for protocol in protocols:
        if protocol == 'http':
            listeners.append(elb.Listener(
                InstanceProtocol='HTTP',
                InstancePort='80',
                LoadBalancerPort='80',
                PolicyNames=listeners_policy_names,
                Protocol='HTTP',
            ))
            elb_ports.append(80)
        elif protocol == 'https':
            listeners.append(elb.Listener(
                InstanceProtocol='HTTP',
                InstancePort='80',
                LoadBalancerPort='443',
                PolicyNames=listeners_policy_names,
                Protocol='HTTPS',
                SSLCertificateId=context['elb']['certificate']
            ))
            elb_ports.append(443)
        else:
            raise RuntimeError("Unknown procotol `%s`" % context['elb']['protocol'])

    template.add_resource(elb.LoadBalancer(
        ELB_TITLE,
        ConnectionDrainingPolicy=elb.ConnectionDrainingPolicy(
            Enabled=True,
            Timeout=60,
        ),
        ConnectionSettings=elb.ConnectionSettings(
            IdleTimeout=context['elb']['idle_timeout']
        ),
        CrossZone=True,
        Instances=map(Ref, ec2_instances),
        # TODO: from configuration
        Listeners=listeners,
        LBCookieStickinessPolicy=cookie_stickiness,
        HealthCheck=elb.HealthCheck(
            Target='TCP:%d' % context['elb']['healthcheck'].get('port', 80),
            HealthyThreshold=str(context['elb']['healthcheck'].get('healthy_threshold', 10)),
            UnhealthyThreshold=str(context['elb']['healthcheck'].get('unhealthy_threshold', 2)),
            Interval=str(context['elb']['healthcheck'].get('interval', 30)),
            Timeout=str(context['elb']['healthcheck'].get('timeout', 30)),
        ),
        SecurityGroups=[Ref(SECURITY_GROUP_ELB_TITLE)],
        Scheme='internet-facing' if elb_is_public else 'internal',
        Subnets=context['elb']['subnets'],
        Tags=elb_tags(context)
    ))

    template.add_resource(security_group(
        SECURITY_GROUP_ELB_TITLE,
        context['project']['aws']['vpc-id'],
        elb_ports
    )) # list of strings or dicts

    dns = external_dns_elb if elb_is_public else internal_dns_elb
    template.add_resource(dns(context))

def render_cloudfront(context, template, origin_hostname):
    origin = CLOUDFRONT_TITLE+'Origin'
    allowed_cnames = ["%s.%s" % (subdomain, context['domain']) for subdomain in context['cloudfront']['subdomains']]
    props = {
        'Aliases': allowed_cnames,
        'DefaultCacheBehavior': cloudfront.DefaultCacheBehavior(
            TargetOriginId=origin,
            ForwardedValues=cloudfront.ForwardedValues(
                QueryString=True
            ),
            ViewerProtocolPolicy='redirect-to-https',
        ),
        'Enabled': True,
        'Origins': [
            cloudfront.Origin(
                DomainName=origin_hostname,
                Id=origin,
                CustomOriginConfig=cloudfront.CustomOrigin(
                    HTTPSPort=443,
                    OriginProtocolPolicy='https-only'
                )
            )
        ],
        'ViewerCertificate': cloudfront.ViewerCertificate(
            AcmCertificateArn=context['cloudfront']['certificate'],
            SslSupportMethod='sni-only'
        )
    }
    template.add_resource(cloudfront.Distribution(
        CLOUDFRONT_TITLE,
        DistributionConfig=cloudfront.DistributionConfig(**props)
    ))

    for dns in external_dns_cloudfront(context):
        template.add_resource(dns)

def render(context):
    template = Template()

    ec2_instances = []
    if context['ec2']:
        ec2_instances = render_ec2(context, template)

    if context['rds_instance_id']:
        rdsinstance(context, template)

    if context['ext']:
        ext_volume(context, template)

    render_sns(context, template)
    render_sqs(context, template)
    render_s3(context, template)

    # TODO: these hostnames will be assigned to an ELB for cluster-size >= 2
    if context['elb']:
        # TODO: we're already passing a mutable object around (template),
        # perhaps elb should just inspect that to get the ec2 instances
        render_elb(context, template, ec2_instances)

    elif context['ec2']:
        ensure(context['ec2']['cluster-size'] == 1,
               "If there is no load balancer, only a single EC2 instance can be assigned a DNS entry: %s" % context)

        if context['full_hostname']:
            template.add_resource(external_dns_ec2(context))

        # ec2 nodes in a cluster DONT get an internal hostname
        if context['int_full_hostname']:
            template.add_resource(internal_dns(context))

    if context['full_hostname']:
        ensure(R53_EXT_TITLE in template.resources.keys(), "You want an external DNS entry but there is no resource configuring it: %s" % context)
        template.add_output(mkoutput("DomainName", "Domain name of the newly created stack instance", Ref(R53_EXT_TITLE)))

    if context['int_full_hostname']:
        ensure(R53_INT_TITLE in template.resources.keys(), "You want an internal DNS entry but there is no resource configuring it: %s" % context)
        template.add_output(mkoutput("IntDomainName", "Domain name of the newly created stack instance", Ref(R53_INT_TITLE)))

    if context['cloudfront']:
        ensure(context['full_hostname'], "A public hostname is required to be pointed at by the Cloudfront CDN")
        render_cloudfront(context, template, origin_hostname=context['full_hostname'])

    return template.to_json()
