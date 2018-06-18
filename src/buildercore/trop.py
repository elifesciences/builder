"""
trop.py is a module that uses the Troposphere library to build up
a AWS Cloudformation (CFN) template dynamically, using values from
the projects file and a bunch of sensible defaults.

It's job is to return the correct CFN JSON given a dictionary of
data called a `context`.

`cfngen.py` is in charge of constructing this data struct and writing
it to the correct file etc."""

from collections import OrderedDict
import copy
from os.path import join
from . import config, utils, bvars
from .config import ConfigurationError
from troposphere import GetAtt, Output, Ref, Template, ec2, rds, sns, sqs, Base64, route53, Parameter, Tags
from troposphere import s3, cloudfront, elasticloadbalancing as elb, elasticache
from functools import partial
from .utils import first, ensure, subdict, lmap, isstr
import logging

LOG = logging.getLogger(__name__)

# TODO: embarassing code. some of these constants should be pulled form project config or given better names.

SECURITY_GROUP_TITLE = "StackSecurityGroup"
SECURITY_GROUP_ELB_TITLE = "ELBSecurityGroup"
EC2_TITLE = 'EC2Instance1'
EC2_TITLE_NODE = 'EC2Instance%d'
ELB_TITLE = 'ElasticLoadBalancer'
RDS_TITLE = "AttachedDB"
RDS_SG_ID = "DBSecurityGroup"
RDS_DB_PG = "RDSDBParameterGroup"
DBSUBNETGROUP_TITLE = 'AttachedDBSubnet'
EXT_TITLE = "ExtraStorage%s"
EXT_MP_TITLE = "MountPoint%s"
R53_EXT_TITLE = "ExtDNS"
R53_INT_TITLE = "IntDNS"
R53_INT_TITLE_NODE = "IntDNS%s"
R53_CDN_TITLE = "CloudFrontCDNDNS%s"
R53_CNAME_TITLE = "CnameDNS%s"
R53_FASTLY_TITLE = "FastlyDNS%s"
CLOUDFRONT_TITLE = 'CloudFrontCDN'
# from http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-route53-aliastarget.html
CLOUDFRONT_HOSTED_ZONE_ID = 'Z2FDTNDATAQYW2'
CLOUDFRONT_ERROR_ORIGIN_ID = 'ErrorsOrigin'
ELASTICACHE_TITLE = 'ElastiCache%s'
ELASTICACHE_SECURITY_GROUP_TITLE = 'ElastiCacheSecurityGroup'
ELASTICACHE_SUBNET_GROUP_TITLE = 'ElastiCacheSubnetGroup'
ELASTICACHE_PARAMETER_GROUP_TITLE = 'ElastiCacheParameterGroup'

KEYPAIR = "KeyName"

def _read_script(script_filename):
    path = join(config.SCRIPTS_PATH, script_filename)
    with open(path, 'r') as fp:
        return fp.read()

def ingress(port, end_port=None, protocol='tcp', cidr='0.0.0.0/0'):
    if not end_port:
        end_port = port
    return ec2.SecurityGroupRule(**{
        'FromPort': port,
        'ToPort': end_port,
        'IpProtocol': protocol,
        'CidrIp': cidr
    })

def complex_ingress(port, struct):
    if struct == True:
        return ingress(port)
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
        'SecurityGroupIngress': [complex_ingress(port, definition) for port, definition in ingress_structs.items()],
    })

def ec2_security(context):
    def _convert_to_dictionary(ports):
        if isinstance(ports, list):
            ports_map = {} 
            for p in ports:
                if isinstance(p, int):
                    ports_map[p] = True
                elif isinstance(p, OrderedDict):
                    ensure(len(p) == 1, "Port can only be defined as a single dictionary")
                    ports_map[p.keys()[0]] = p.values()[0]
                else:
                    raise ValueError("Invalid port definition: %s" % p)
            return ports_map
        return ports
    ports = _convert_to_dictionary(context['project']['aws'].get('ports', {}))
    security_group_ports = _convert_to_dictionary(context['ec2']['security-group'].get('ports', {}))
    ports.update(security_group_ports)

    ensure(len(ports) > 0,
           "Empty `ports` configuration in `aws` for '%s'" % context['stackname'])

    return security_group(
        SECURITY_GROUP_TITLE,
        context['project']['aws']['vpc-id'],
        ports
    )

def rds_security(context):
    """returns a security group for the rds instance.

    this security group only allows access within the subnet, not because of the ip address range but because this is dealt with in the subnet configuration"""
    engine_ports = {
        'postgres': 5432,
        'mysql': 3306
    }
    ingress_ports = {engine_ports[context['project']['aws']['rds']['engine'].lower()]: True}
    return security_group("VPCSecurityGroup",
                          context['project']['aws']['vpc-id'],
                          ingress_ports,
                          "RDS DB security group")

#
#
#

def _generic_tags(context, name=True):
    tags = {
        'Project': context['project_name'], # journal
        'Environment': context['instance_id'], # stack instance id
        # the name AWS Console uses to label an instance
        'Cluster': context['stackname'], # ll: journal--prod

        # potential new tags
        # 'Masterless': context['masterless'] # True or False
    }
    tags['Name'] = context['stackname'] # ll: journal-prod
    return tags

def instance_tags(context, node=None):
    # NOTE: RDS and Elasticache instances also call this function
    tags = _generic_tags(context)
    if node:
        # this instance is part of a cluster
        tags.update({
            'Name': '%s--%d' % (context['stackname'], node), # ll: journal--prod--1
            'Node': node, # ll: 1
        })
    return [ec2.Tag(key, str(value)) for key, value in tags.items()]

def elb_tags(context):
    tags = _generic_tags(context)
    tags.update({
        'Name': '%s--elb' % context['stackname'], # ll: journal--prod--elb
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
    """returns a subset of given context data with some extra node information
    that will be encoded and stored on the ec2 instance"""
    buildvars = copy.deepcopy(context)

    # preseve some of the project data. all of it is too much
    keepers = [
        'formula-repo',
        'formula-dependencies'
    ]
    buildvars['project'] = subdict(buildvars['project'], keepers)

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

    clean_server = _read_script('.clean-server.sh.fragment') # this file duplicates scripts/prep-stack.sh
    project_ec2 = {
        "ImageId": lu('project.aws.ec2.ami'),
        "InstanceType": context['ec2']['type'], # t2.small, m1.medium, etc
        "KeyName": Ref(KEYPAIR),
        "SecurityGroupIds": [Ref(SECURITY_GROUP_TITLE)],
        "SubnetId": subnet_id, # ll: "subnet-1d4eb46a"
        "Tags": instance_tags(context, node),

        # https://alestic.com/2010/12/ec2-user-data-output/
        "UserData": Base64("""#!/bin/bash
set -x
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo %s > /etc/build-vars.json.b64

%s""" % (buildvars_serialization, clean_server)),
    }
    return ec2.Instance(EC2_TITLE_NODE % node, **project_ec2)

def rdsdbparams(context, template):
    if not context.get('rds_params'):
        return None
    lu = partial(utils.lu, context)
    engine = lu('project.aws.rds.engine')
    version = str(lu('project.aws.rds.version'))
    name = RDS_DB_PG
    dbpg = rds.DBParameterGroup(name, **{
        'Family': "%s%s" % (engine.lower(), version), # ll: mysql5.6, postgres9.4
        'Description': '%s (%s) custom parameters' % (context['project_name'], context['instance_id']),
        'Parameters': context['rds_params']
    })
    template.add_resource(dbpg)
    return Ref(dbpg)

def render_rds(context, template):
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

    # rds parameter group. None or a Ref
    param_group_ref = rdsdbparams(context, template)

    tags = instance_tags(context)
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
        # something is converting this value to an int from a float :(
        "EngineVersion": str(lu('project.aws.rds.version')), # 'defaults.aws.rds.storage')),
        'MasterUsername': lu('rds_username'), # pillar data is now UNavailable
        'MasterUserPassword': lu('rds_password'),
        'BackupRetentionPeriod': lu('project.aws.rds.backup-retention'),
        'DeletionPolicy': lu('rds.deletion-policy'),
        "Tags": tags,
        "AllowMajorVersionUpgrade": False, # default? not specified.
        "AutoMinorVersionUpgrade": True, # default
    }

    if param_group_ref:
        data['DBParameterGroupName'] = param_group_ref

    rdbi = rds.DBInstance(RDS_TITLE, **data)
    lmap(template.add_resource, [rsn, rdbi, vpcdbsg])

    outputs = [
        mkoutput("RDSHost", "Connection endpoint for the DB cluster", (RDS_TITLE, "Endpoint.Address")),
        mkoutput("RDSPort", "The port number on which the database accepts connections", (RDS_TITLE, "Endpoint.Port")),
    ]
    lmap(template.add_output, outputs)

def render_ext_volume(context, context_ext, template, node=1):
    vtype = context_ext.get('type', 'standard')
    # who cares what gp2 stands for? everyone knows what 'ssd' and 'standard' mean ...
    if vtype == 'ssd':
        vtype = 'gp2'

    args = {
        "Size": str(context_ext['size']),
        "AvailabilityZone": GetAtt(EC2_TITLE_NODE % node, "AvailabilityZone"),
        "VolumeType": vtype,
        "Tags": instance_tags(context, node),
    }
    ec2v = ec2.Volume(EXT_TITLE % node, **args)

    args = {
        "InstanceId": Ref(EC2_TITLE_NODE % node),
        "VolumeId": Ref(ec2v),
        "Device": context_ext.get('device'),
    }
    ec2va = ec2.VolumeAttachment(EXT_MP_TITLE % node, **args)
    lmap(template.add_resource, [ec2v, ec2va])

def external_dns_ec2_single(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        Comment="External DNS record for EC2",
        Name=context['full_hostname'] + '.',
        Type="A",
        TTL="60",
        ResourceRecords=[GetAtt(EC2_TITLE, "PublicIp")],
    )
    return dns_record

def internal_dns_ec2_single(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['int_domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        Comment="Internal DNS record for EC2",
        Name=context['int_full_hostname'] + '.',
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
    i = 1
    for cdn_hostname in context['cloudfront']['subdomains']:
        if _is_domain_2nd_level(cdn_hostname):
            hostedzone = cdn_hostname + "."
        else:
            hostedzone = context['domain'] + "."
        dns_records.append(route53.RecordSetType(
            R53_CDN_TITLE % i,
            HostedZoneName=hostedzone,
            Comment="External DNS record for Cloudfront distribution",
            Name=cdn_hostname + ".",
            Type="A",
            AliasTarget=route53.AliasTarget(
                CLOUDFRONT_HOSTED_ZONE_ID,
                GetAtt(CLOUDFRONT_TITLE, "DomainName")
            )
        ))
        i = i + 1

    return dns_records

def external_dns_fastly(context):
    "a Fastly CDN requires additional CNAME DNS entries pointing at it"
    ensure(isinstance(context['domain'], str), "A 'domain' must be specified for CNAMEs to be built: %s" % context)

    # may be used to point to TLS servers

    def entry(hostname, i):
        if _is_domain_2nd_level(hostname):
            hostedzone = hostname + "."
            ip_addresses = context['fastly']['dns']['a']
            return route53.RecordSetType(
                R53_FASTLY_TITLE % (i + 1), # expecting more than one entry (aliases), so numbering them immediately
                HostedZoneName=hostedzone,
                Name=hostname,
                Type="A",
                TTL="60",
                ResourceRecords=ip_addresses,
            )
            raise ConfigurationError("2nd-level domains aliases are not supported yet by builder. See https://docs.fastly.com/guides/basic-configuration/using-fastly-with-apex-domains")

        hostedzone = context['domain'] + "."
        cname = context['fastly']['dns']['cname']
        return route53.RecordSetType(
            R53_FASTLY_TITLE % (i + 1), # expecting more than one entry (aliases), so numbering them immediately
            HostedZoneName=hostedzone,
            Name=hostname,
            Type="CNAME",
            TTL="60",
            ResourceRecords=[cname],
        )
    return [entry(hostname, i) for i, hostname in enumerate(context['fastly']['subdomains'])]

#
# render_* funcs
#

def _sanitize_title(string):
    return "".join(map(str.capitalize, string.split("-")))

def render_ec2(context, template):
    # all ec2 nodes in a cluster share the same security group
    secgroup = ec2_security(context)
    template.add_resource(secgroup)
    suppressed = context['ec2'].get('suppressed', [])

    ec2_instances = {}
    for node in range(1, context['ec2']['cluster-size'] + 1):
        if node in suppressed:
            continue
        instance = ec2instance(context, node)
        ec2_instances[node] = instance
        template.add_resource(instance)

        outputs = [
            mkoutput("AZ%d" % node, "Availability Zone of the newly created EC2 instance", (EC2_TITLE_NODE % node, "AvailabilityZone")),
            mkoutput("InstanceId%d" % node, "InstanceId of the newly created EC2 instance", Ref(EC2_TITLE_NODE % node)),
            mkoutput("PrivateIP%d" % node, "Private IP address of the newly created EC2 instance", (EC2_TITLE_NODE % node, "PrivateIp")),
            mkoutput("PublicIP%d" % node, "Public IP address of the newly created EC2 instance", (EC2_TITLE_NODE % node, "PublicIp")),
        ]
        lmap(template.add_output, outputs)

    # all ec2 nodes in a cluster share the same keypair
    template.add_parameter(Parameter(KEYPAIR, **{
        "Type": "String",
        "Description": "EC2 KeyPair that enables SSH access to this instance",
    }))
    return ec2_instances

def render_ec2_dns(context, template):
    # single ec2 node may get an external hostname
    if context['full_hostname'] and not context['elb']:
        ensure(context['ec2']['cluster-size'] <= 1,
               "If there is no load balancer, multiple EC2 instances cannot be assigned a single DNS entry")

        if context['ec2']['cluster-size'] == 1:
            template.add_resource(external_dns_ec2_single(context))
            [template.add_resource(cname) for cname in cnames(context)]

    # single ec2 node may get an internal hostname
    if context['int_full_hostname'] and not context['elb']:
        ensure(context['ec2']['cluster-size'] == 1,
               "If there is no load balancer, only a single EC2 instance can be assigned a DNS entry")
        template.add_resource(internal_dns_ec2_single(context))

    # ec2 nodes in a cluster may get a different internal hostname each
    if context['ec2']['dns-internal']:
        for node in range(1, context['ec2']['cluster-size'] + 1):
            hostedzone = context['int_domain'] + "."
            dns_record = route53.RecordSetType(
                R53_INT_TITLE_NODE % node,
                HostedZoneName=hostedzone,
                Comment="Internal DNS record for EC2 node %s" % node,
                Name=context['int_node_hostname'] % node,
                Type="A",
                TTL="60",
                ResourceRecords=[GetAtt(EC2_TITLE_NODE % node, "PrivateIp")],
            )
            template.add_resource(dns_record)

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
            'DeletionPolicy': context['s3'][bucket_name]['deletion-policy'].capitalize(),
            'Tags': s3.Tags(**_generic_tags(context, name=False)),
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
            _add_bucket_policy(template, bucket_title, bucket_name)

        if context['s3'][bucket_name]['public']:
            _add_bucket_policy(template, bucket_title, bucket_name)
            props['AccessControl'] = s3.PublicRead

        template.add_resource(s3.Bucket(
            bucket_title,
            BucketName=bucket_name,
            **props
        ))

def _add_bucket_policy(template, bucket_title, bucket_name):
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

def _elb_protocols(context):
    if isstr(context['elb']['protocol']):
        return [context['elb']['protocol']]
    return context['elb']['protocol']

def render_elb(context, template, ec2_instances):
    elb_is_public = True if context['full_hostname'] else False
    listeners_policy_names = []

    app_cookie_stickiness_policy = []
    lb_cookie_stickiness_policy = []
    if context['elb']['stickiness']:
        if context['elb']['stickiness']['type'] == 'cookie':
            app_cookie_stickiness_policy = [elb.AppCookieStickinessPolicy(
                CookieName=context['elb']['stickiness']['cookie-name'],
                PolicyName='AppCookieStickinessPolicy'
            )]
            listeners_policy_names.append('AppCookieStickinessPolicy')
        elif context['elb']['stickiness']['type'] == 'browser':
            lb_cookie_stickiness_policy = [elb.LBCookieStickinessPolicy(
                PolicyName='BrowserSessionLongCookieStickinessPolicy'
            )]
            listeners_policy_names.append('BrowserSessionLongCookieStickinessPolicy')
        else:
            raise ValueError('Unsupported stickiness: %s' % context['elb']['stickiness'])

    protocols = _elb_protocols(context)

    listeners = []
    elb_ports = {}
    for protocol in protocols:
        if protocol == 'http':
            listeners.append(elb.Listener(
                InstanceProtocol='HTTP',
                InstancePort='80',
                LoadBalancerPort='80',
                PolicyNames=listeners_policy_names,
                Protocol='HTTP',
            ))
            elb_ports[80] = True
        elif protocol == 'https':
            listeners.append(elb.Listener(
                InstanceProtocol='HTTP',
                InstancePort='80',
                LoadBalancerPort='443',
                PolicyNames=listeners_policy_names,
                Protocol='HTTPS',
                SSLCertificateId=context['elb']['certificate']
            ))
            elb_ports[443] = True
        else:
            raise RuntimeError("Unknown procotol `%s`" % context['elb']['protocol'])

    for _, listener in context['elb']['additional_listeners'].items():
        listeners.append(elb.Listener(
            InstanceProtocol='HTTP',
            InstancePort=str(listener['port']),
            LoadBalancerPort=str(listener['port']),
            PolicyNames=listeners_policy_names,
            Protocol=listener['protocol'].upper(),
            SSLCertificateId=context['elb']['certificate']
        ))
        elb_ports[listener['port']] = True

    template.add_resource(elb.LoadBalancer(
        ELB_TITLE,
        AppCookieStickinessPolicy=app_cookie_stickiness_policy,
        ConnectionDrainingPolicy=elb.ConnectionDrainingPolicy(
            Enabled=True,
            Timeout=60,
        ),
        ConnectionSettings=elb.ConnectionSettings(
            IdleTimeout=context['elb']['idle_timeout']
        ),
        CrossZone=True,
        Instances=lmap(Ref, ec2_instances.values()),
        # TODO: from configuration
        Listeners=listeners,
        LBCookieStickinessPolicy=lb_cookie_stickiness_policy,
        HealthCheck=elb.HealthCheck(
            Target=_elb_healthcheck_target(context),
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

    if any([context['full_hostname'], context['int_full_hostname']]):
        dns = external_dns_elb if elb_is_public else internal_dns_elb
        template.add_resource(dns(context))
    if context['full_hostname']:
        [template.add_resource(cname) for cname in cnames(context)]

def _elb_healthcheck_target(context):
    if context['elb']['healthcheck']['protocol'] == 'tcp':
        return 'TCP:%d' % context['elb']['healthcheck'].get('port', 80)
    elif context['elb']['healthcheck']['protocol'] == 'http':
        return 'HTTP:%s%s' % (context['elb']['healthcheck']['port'], context['elb']['healthcheck']['path'])
    else:
        raise ValueError("Unsupported healthcheck protocol: %s" % context['elb']['healthcheck']['protocol'])

def render_cloudfront(context, template, origin_hostname):
    if not context['cloudfront']['origins']:
        ensure(context['full_hostname'], "A public hostname is required to be pointed at by the Cloudfront CDN")

    allowed_cnames = context['cloudfront']['subdomains'] + context['cloudfront']['subdomains-without-dns']

    def _cookies(cookies):
        if cookies:
            return cloudfront.Cookies(
                Forward='whitelist',
                WhitelistedNames=cookies
            )
        return cloudfront.Cookies(
            Forward='none'
        )

    if context['cloudfront']['origins']:
        origins = [
            cloudfront.Origin(
                DomainName=o['hostname'],
                Id=o_id,
                CustomOriginConfig=cloudfront.CustomOrigin(
                    HTTPSPort=443,
                    OriginProtocolPolicy='https-only'
                )
            )
            for o_id, o in context['cloudfront']['origins'].items()
        ]
        origin = origins[0].Id
    else:
        origin = CLOUDFRONT_TITLE + 'Origin'
        origins = [
            cloudfront.Origin(
                DomainName=origin_hostname,
                Id=origin,
                CustomOriginConfig=cloudfront.CustomOrigin(
                    HTTPSPort=443,
                    OriginProtocolPolicy='https-only'
                )
            )
        ]
    props = {
        'Aliases': allowed_cnames,
        'CacheBehaviors': [],
        'DefaultCacheBehavior': cloudfront.DefaultCacheBehavior(
            AllowedMethods=['DELETE', 'GET', 'HEAD', 'OPTIONS', 'PATCH', 'POST', 'PUT'],
            CachedMethods=['GET', 'HEAD'],
            Compress=context['cloudfront']['compress'],
            DefaultTTL=context['cloudfront']['default-ttl'],
            TargetOriginId=origin,
            ForwardedValues=cloudfront.ForwardedValues(
                Cookies=_cookies(context['cloudfront']['cookies']),
                Headers=context['cloudfront']['headers'], # 'whitelisted' headers
                QueryString=True
            ),
            ViewerProtocolPolicy='redirect-to-https',
        ),
        'Enabled': True,
        'HttpVersion': 'http2',
        'Origins': origins,
        'ViewerCertificate': cloudfront.ViewerCertificate(
            IamCertificateId=context['cloudfront']['certificate_id'],
            SslSupportMethod='sni-only'
        )
    }

    def _cache_behavior(origin_id, pattern, headers=None, cookies=None):
        return cloudfront.CacheBehavior(
            TargetOriginId=origin_id,
            DefaultTTL=context['cloudfront']['default-ttl'],
            ForwardedValues=cloudfront.ForwardedValues(
                Cookies=_cookies(cookies),
                QueryString=False,
                Headers=headers if headers else []
            ),
            PathPattern=pattern,
            ViewerProtocolPolicy='allow-all',
        )

    if context['cloudfront']['errors']:
        props['Origins'].append(cloudfront.Origin(
            DomainName=context['cloudfront']['errors']['domain'],
            # TODO: constant
            Id=CLOUDFRONT_ERROR_ORIGIN_ID,
            # no advantage in using cloudfront.S3Origin for public buckets
            CustomOriginConfig=cloudfront.CustomOrigin(
                HTTPSPort=443,
                OriginProtocolPolicy='https-only' if context['cloudfront']['errors']['protocol'] == 'https' else 'http-only'
            )
        ))
        props['CacheBehaviors'].append(_cache_behavior(
            CLOUDFRONT_ERROR_ORIGIN_ID,
            context['cloudfront']['errors']['pattern'],
        ))
        props['CustomErrorResponses'] = [
            cloudfront.CustomErrorResponse(
                ErrorCode=code,
                ResponseCode=code,
                ResponsePagePath=page
            ) for code, page in context['cloudfront']['errors']['codes'].items()
        ]

    if context['cloudfront']['logging']:
        props['Logging'] = cloudfront.Logging(
            Bucket="%s.s3.amazonaws.com" % context['cloudfront']['logging']['bucket'],
            Prefix="%s/" % context['stackname']
        )

    if context['cloudfront']['origins']:
        props['CacheBehaviors'].extend([
            _cache_behavior(
                o_id,
                o['pattern'],
                headers=o['headers'],
                cookies=o['cookies']
            )
            for o_id, o in context['cloudfront']['origins'].items()
            if o['pattern']
        ])

    template.add_resource(cloudfront.Distribution(
        CLOUDFRONT_TITLE,
        DistributionConfig=cloudfront.DistributionConfig(**props)
    ))

    for dns in external_dns_cloudfront(context):
        template.add_resource(dns)

def render_fastly(context, template):
    "WARNING: only creates Route53 DNS entries, delegating the rest of the setup to Terraform"
    for dns in external_dns_fastly(context):
        template.add_resource(dns)

def elasticache_security_group(context):
    "returns a security group for the ElastiCache instances. this security group only allows access within the VPC"
    engine_ports = {
        'redis': 6379,
    }
    ingress_ports = {engine_ports[context['elasticache']['engine']]: True}
    return security_group(ELASTICACHE_SECURITY_GROUP_TITLE,
                          context['project']['aws']['vpc-id'],
                          ingress_ports,
                          "ElastiCache security group")

def elasticache_default_parameter_group(context):
    return elasticache.ParameterGroup(
        ELASTICACHE_PARAMETER_GROUP_TITLE,
        CacheParameterGroupFamily='redis2.8',
        Description='ElastiCache parameter group for %s' % context['stackname'],
        Properties=context['elasticache']['configuration']
    )

def elasticache_overridden_parameter_group(context, cluster_context, cluster):
    return elasticache.ParameterGroup(
        "%s%d" % (ELASTICACHE_PARAMETER_GROUP_TITLE, cluster),
        CacheParameterGroupFamily='redis2.8',
        Description='ElastiCache parameter group for %s cluster %d' % (context['stackname'], cluster),
        Properties=cluster_context['configuration']
    )

def render_elasticache(context, template):
    ensure(context['elasticache']['engine'] == 'redis', 'We only support Redis as ElastiCache engine at this time')

    cache_security_group = elasticache_security_group(context)
    template.add_resource(cache_security_group)

    subnet_group = elasticache.SubnetGroup(
        ELASTICACHE_SUBNET_GROUP_TITLE,
        Description="a group of subnets for this cache instance.",
        SubnetIds=context['elasticache']['subnets']
    )
    template.add_resource(subnet_group)

    parameter_group = elasticache_default_parameter_group(context)

    suppressed = context['elasticache'].get('suppressed', [])
    default_parameter_group_use = False
    for cluster in range(1, context['elasticache']['clusters'] + 1):
        if cluster in suppressed:
            continue

        cluster_context = overridden_component(context, 'elasticache', cluster, ['type', 'version', 'az', 'configuration'])

        if cluster_context['configuration'] != context['elasticache']['configuration']:
            cluster_parameter_group = elasticache_overridden_parameter_group(context, cluster_context, cluster)
            template.add_resource(cluster_parameter_group)
            cluster_cache_parameter_group_name = Ref(cluster_parameter_group)
        else:
            cluster_cache_parameter_group_name = Ref(parameter_group)
            default_parameter_group_use = True

        cluster_title = ELASTICACHE_TITLE % cluster
        template.add_resource(elasticache.CacheCluster(
            cluster_title,
            CacheNodeType=cluster_context['type'],
            CacheParameterGroupName=cluster_cache_parameter_group_name,
            CacheSubnetGroupName=Ref(subnet_group),
            Engine='redis',
            EngineVersion=cluster_context['version'],
            PreferredAvailabilityZone=cluster_context['az'],
            # we only support Redis, and it only supports 1 node
            NumCacheNodes=1,
            Tags=Tags(**_generic_tags(context)),
            VpcSecurityGroupIds=[Ref(cache_security_group)],
        ))

        outputs = [
            mkoutput("ElastiCacheHost%s" % cluster, "The hostname on which the cache accepts connections", (cluster_title, "RedisEndpoint.Address")),
            mkoutput("ElastiCachePort%s" % cluster, "The port number on which the cache accepts connections", (cluster_title, "RedisEndpoint.Port")),
        ]
        lmap(template.add_output, outputs)

    if default_parameter_group_use:
        template.add_resource(parameter_group)

def render(context):
    template = Template()

    ec2_instances = render_ec2(context, template) if context['ec2'] else {}
    context['rds_instance_id'] and render_rds(context, template)

    # TODO: move to a render_ext
    if context['ext']:
        # backward compatibility: ext is still specified outside of ec2 rather than as a sub-key
        context['ec2']['ext'] = context['ext']
        all_nodes = list(ec2_instances.keys())
        for node in all_nodes:
            overrides = context['ec2'].get('overrides', {}).get(node, {})
            overridden_context = copy.deepcopy(context)
            overridden_context['ext'].update(overrides.get('ext', {}))
            node_context = overridden_component(context, 'ec2', node, ['ext'])
            render_ext_volume(overridden_context, node_context.get('ext', {}), template, node)

    render_sns(context, template)
    render_sqs(context, template)
    render_s3(context, template)

    # hostname is assigned to an ELB, which has priority over
    # N>=1 EC2 instances
    context['elb'] and render_elb(context, template, ec2_instances)
    context['ec2'] and render_ec2_dns(context, template)

    add_outputs(context, template)

    context['cloudfront'] and render_cloudfront(context, template, origin_hostname=context['full_hostname'])
    context['fastly'] and render_fastly(context, template)
    context['elasticache'] and render_elasticache(context, template)

    return template.to_json()

def add_outputs(context, template):
    if R53_EXT_TITLE in template.resources.keys():
        template.add_output(mkoutput("DomainName", "Domain name of the newly created stack instance", Ref(R53_EXT_TITLE)))

    if R53_INT_TITLE in template.resources.keys():
        template.add_output(mkoutput("IntDomainName", "Domain name of the newly created stack instance", Ref(R53_INT_TITLE)))


def cnames(context):
    "additional CNAME DNS entries pointing to full_hostname"
    ensure(isstr(context['domain']), "A 'domain' must be specified for CNAMEs to be built")

    def entry(hostname, i):
        if _is_domain_2nd_level(hostname):
            # must be an alias as it is a 2nd-level domain like elifesciences.net
            hostedzone = hostname + "."
            ensure(context['elb'], "2nd-level domains aliases are only supported for ELBs")
            return route53.RecordSetType(
                R53_CNAME_TITLE % (i + 1),
                HostedZoneName=hostedzone,
                Name=hostname,
                Type="A",
                AliasTarget=route53.AliasTarget(
                    GetAtt(ELB_TITLE, "CanonicalHostedZoneNameID"),
                    GetAtt(ELB_TITLE, "DNSName")
                )
            )
        hostedzone = context['domain'] + "."
        return route53.RecordSetType(
            R53_CNAME_TITLE % (i + 1),
            HostedZoneName=hostedzone,
            Name=hostname,
            Type="CNAME",
            TTL="60",
            ResourceRecords=[context['full_hostname']],
        )
    return [entry(hostname, i) for i, hostname in enumerate(context['subdomains'])]

def _is_domain_2nd_level(hostname):
    "returns True if hostname is a 2nd level TLD, e.g. elifesciences.org or elifesciences.net"
    return hostname.count(".") == 1

def overridden_component(context, component, index, allowed):
    "two-level merging of overrides into one of context's componenets"
    overrides = context[component].get('overrides', {}).get(index, {})
    for element in overrides:
        ensure(element in allowed, "`%s` override is not allowed for single elasticache clusters" % element)
    overridden_context = copy.deepcopy(context)
    overridden_context[component].pop('overrides', None)
    for key, value in overrides.items():
        if isinstance(overridden_context[component][key], dict):
            overridden_context[component][key].update(value)
        else:
            overridden_context[component][key] = value
    return overridden_context[component]
