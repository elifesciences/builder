"""`trop.py` is a module that uses the Troposphere library to build up
an AWS CloudFormation template dynamically using values from the
'context', a dictionary of data built up in `cfngen.py` derived from
the project file (`projects/elife.yaml`):

   projects file -> context -> troposphere.py -> cloudformation json

The non-AWS pipeline is similar:

                            -> terraform.py   -> terraform json

see also `terraform.py`"""

from collections import OrderedDict
from os.path import join
from . import config, utils, bvars, aws
from .config import ConfigurationError
from troposphere import GetAtt, Output, Ref, Template, ec2, rds, sns, sqs, Base64, route53, Parameter, Tags, docdb
from troposphere import s3, cloudfront, elasticloadbalancing as elb, elasticloadbalancingv2 as alb, elasticache
from functools import partial
from .utils import ensure, subdict, lmap, isstr, deepcopy
import logging

LOG = logging.getLogger(__name__)

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
R53_EXT_TITLE_NODE = "ExtDNS%s"
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
ALB_TITLE = 'ElasticLoadBalancerV2'

KEYPAIR = "KeyName"

# --- utils, used by by more than one resource

def _remove_if_none(data, key_list):
    """deletes a list of keys from given `data` if keyed value is `None`.
    Cloudformation may not accept `null` for a value but will accept the absence of it's key."""
    for key in key_list:
        if data[key] is None:
            del data[key]

def _sanitize_title(string):
    return "".join(map(str.capitalize, string.split("-")))

def _convert_ports_to_dictionary(ports):
    if isinstance(ports, list):
        ports_map = OrderedDict()
        for p in ports:
            if isinstance(p, int):
                ports_map[p] = {}
            elif isinstance(p, dict):
                ensure(len(p) == 1, "Single port definition cannot contain more than one value")
                from_port = list(p.keys())[0]
                configuration = list(p.values())[0]
                ports_map[from_port] = configuration
            else:
                raise ValueError("Invalid port definition: %s" % (p,))
    elif isinstance(ports, dict):
        ports_map = OrderedDict()
        for p, configuration in ports.items():
            if isinstance(configuration, bool):
                # temporary
                ports_map[p] = {}
            elif isinstance(configuration, int):
                ports_map[p] = {'guest': configuration}
            elif isinstance(configuration, OrderedDict):
                ports_map[p] = configuration
            else:
                raise ValueError("Invalid port definition: %s => %s" % (p, configuration))
    else:
        raise ValueError("Invalid ports definition: %s" % ports)

    return ports_map

def merge_ports(ports, another):
    ports = OrderedDict(ports)
    ports.update(another)
    return ports

def convert_ports_dict_to_troposphere(ports):
    def _port_to_dict(port, configuration):
        return ec2.SecurityGroupRule(**{
            'FromPort': port,
            'ToPort': configuration.get('guest', port),
            'IpProtocol': configuration.get('protocol', 'tcp'),
            'CidrIp': configuration.get('cidr-ip', '0.0.0.0/0'),
        })
    return [_port_to_dict(port, configuration) for port, configuration in ports.items()]

def security_group(group_id, vpc_id, ingress_data, description=""):
    return ec2.SecurityGroup(group_id, **{
        'GroupDescription': description or 'security group',
        'VpcId': vpc_id,
        'SecurityGroupIngress': convert_ports_dict_to_troposphere(ingress_data),
    })

def _instance_tags(context, node=None):
    """returns a dictionary of common tags for an instance.
    Passing in the node's number will include node-specific tags."""
    tags = aws.generic_tags(context)
    if node:
        # this instance is part of a cluster
        tags.update({
            'Name': '%s--%d' % (context['stackname'], node), # "journal--prod--1"
            'Node': node, # "1"
        })
    return tags

def instance_tags(context, node=None, single_tag_obj=False):
    """same as `_instance_tags`, but returns a list of `Tag` objects.
    When `single_tag_obj` is `True`, a single `Tags` (plural) object is returned as ewer
    troposphere resources use `troposphere.Tags` to model a collection of `Tag` objects."""
    data = _instance_tags(context, node)
    if single_tag_obj:
        return Tags(data)
    return [ec2.Tag(key, str(value)) for key, value in data.items()]

def mkoutput(title, desc, val):
    if isinstance(val, tuple):
        val = GetAtt(val[0], val[1])
    return Output(title, Description=desc, Value=val)

def overridden_component(context, component, index, allowed, interesting=None):
    "two-level merging of overrides into one of context's components"
    if not interesting:
        interesting = allowed
    overrides = context[component].get('overrides', {}).get(index, {})
    for element in overrides:
        ensure(element in allowed, "`%s` override is not allowed for `%s` clusters" % (element, component))
    overridden_context = deepcopy(context)
    overridden_context[component].pop('overrides', None)
    for key, value in overrides.items():
        if key not in interesting:
            continue
        assert key in overridden_context[component], "Can't override `%s` as it's not already a key in `%s`" % (key, overridden_context[component].keys())
        if isinstance(overridden_context[component][key], dict):
            overridden_context[component][key].update(value)
        else:
            overridden_context[component][key] = value
    return overridden_context[component]

def _is_domain_2nd_level(hostname):
    """returns True if hostname is a 2nd level TLD.
    e.g. the 'elifesciences' in 'journal.elifesciences.org'.
    '.org' would be the first-level domain name, and 'journal' would be the third-level or 'sub' domain name."""
    return hostname.count(".") == 1

def cnames(context):
    "additional CNAME DNS entries pointing to full_hostname"
    ensure(isstr(context['domain']), "A 'domain' must be specified for CNAMEs to be built")

    def entry(hostname, i):
        if _is_domain_2nd_level(hostname):
            # must be an alias as it is a 2nd-level domain like elifesciences.net
            ensure(context['elb'] or context['alb'], "2nd-level domain aliases are only supported for ELBs and ALBs")

            hostedzone = hostname + "." # "elifesciences.org."

            # ELBs take precendence.
            # disabling the ELB during migration will replace the ELB DNS entries with ALB DNS entries.
            target = ELB_TITLE if context['elb'] else ALB_TITLE

            return route53.RecordSetType(
                R53_CNAME_TITLE % (i + 1),
                HostedZoneName=hostedzone,
                Name=hostname,
                Type="A",
                AliasTarget=route53.AliasTarget(
                    GetAtt(target, "CanonicalHostedZoneNameID"),
                    GetAtt(target, "DNSName")
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

#
# render_* functions
#

# --- ec2

def build_vars(context, node):
    """returns a subset of given context data with some extra node information
    that will be encoded and stored on the ec2 instance at /etc/build-vars.json.b64"""
    buildvars = deepcopy(context)

    # preseve some of the project data. all of it is too much
    keepers = [
        'formula-repo',
        'formula-dependencies'
    ]
    buildvars['project'] = subdict(buildvars['project'], keepers)

    buildvars['node'] = node
    buildvars['nodename'] = "%s--%s" % (context['stackname'], node) # "journal--prod--1"

    return buildvars

def ec2instance(context, node):
    lu = partial(utils.lu, context)
    buildvars = build_vars(context, node)
    buildvars_serialization = bvars.encode_bvars(buildvars)

    odd = node % 2 == 1
    subnet_id = lu('aws.subnet-id') if odd else lu('aws.redundant-subnet-id')
    clean_server_script = open(join(config.SCRIPTS_PATH, '.clean-server.sh.fragment'), 'r').read()
    project_ec2 = {
        "ImageId": lu('ec2.ami'),
        "InstanceType": lu('ec2.type'), # "t2.small", "m1.medium", etc
        "KeyName": Ref(KEYPAIR),
        "SecurityGroupIds": [Ref(SECURITY_GROUP_TITLE)],
        "SubnetId": subnet_id, # "subnet-1d4eb46a"
        "Tags": instance_tags(context, node),

        # send script output to AWS EC2 console, syslog and /var/log/user-data.log
        # - https://alestic.com/2010/12/ec2-user-data-output/
        "UserData": Base64("""#!/bin/bash
set -x
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo %s > /etc/build-vars.json.b64

%s""" % (buildvars_serialization, clean_server_script)),
    }

    if lu('ec2.cpu-credits') != 'standard':
        project_ec2["CreditSpecification"] = ec2.CreditSpecification(
            CPUCredits=lu('ec2.cpu-credits'),
        )

    if context['ec2'].get('root'):
        project_ec2['BlockDeviceMappings'] = [{
            'DeviceName': '/dev/sda1',
            'Ebs': {
                'VolumeSize': context['ec2']['root']['size'],
                'VolumeType': context['ec2']['root'].get('type', 'standard'),
                # unfortunately root volumes do not support Tags:
                # https://blog.cloudability.com/two-solutions-for-tagging-elusive-aws-ebs-volumes/
            }
        }]
    return ec2.Instance(EC2_TITLE_NODE % node, **project_ec2)

def render_ext_volume(context, context_ext, template, actual_ec2_instances, node=1):
    vtype = context_ext.get('type', 'standard') # todo: no default values here, push this into cfngen.py

    if node in actual_ec2_instances:
        availability_zone = GetAtt(EC2_TITLE_NODE % node, "AvailabilityZone")
    else:
        availability_zone = context['aws']['availability-zone'] if node % 2 == 1 else context['aws']['redundant-availability-zone']

    args = {
        "Size": str(context_ext['size']),
        "AvailabilityZone": availability_zone,
        "VolumeType": vtype,
        "Tags": instance_tags(context, node),
    }
    ec2v = ec2.Volume(EXT_TITLE % node, **args)
    template.add_resource(ec2v)

    if node in actual_ec2_instances:
        args = {
            "InstanceId": Ref(EC2_TITLE_NODE % node),
            "VolumeId": Ref(ec2v),
            "Device": context_ext.get('device'),
        }
        template.add_resource(ec2.VolumeAttachment(EXT_MP_TITLE % node, **args))

def render_ext(context, template, cluster_size, actual_ec2_instances):
    # backward compatibility: ext is still specified outside of ec2 rather than as a sub-key
    context['ec2']['ext'] = context['ext']
    for node in range(1, cluster_size + 1):
        overrides = context['ec2'].get('overrides', {}).get(node, {})
        overridden_context = deepcopy(context)
        overridden_context['ext'].update(overrides.get('ext', {}))
        # TODO: extract `allowed` variable
        node_context = overridden_component(context, 'ec2', index=node, allowed=['type', 'ext'])
        render_ext_volume(overridden_context, node_context.get('ext', {}), template, actual_ec2_instances, node)

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

def ec2_security(context):
    ec2_port_data = context['ec2']['ports']
    ec2_ports = _convert_ports_to_dictionary(ec2_port_data)
    security_group_data = context['ec2']['security-group'].get('ports', {})
    security_group_ports = _convert_ports_to_dictionary(security_group_data)
    ingress = merge_ports(ec2_ports, security_group_ports)

    return security_group(
        SECURITY_GROUP_TITLE,
        context['aws']['vpc-id'],
        ingress
    )

def render_ec2(context, template):
    # all ec2 nodes in a cluster share the same security group
    secgroup = ec2_security(context)
    template.add_resource(secgroup)
    suppressed = context['ec2'].get('suppressed', [])

    ec2_instances = {}
    for node in range(1, context['ec2']['cluster-size'] + 1):
        if node in suppressed:
            continue

        overridden_context = deepcopy(context)
        overridden_ec2 = overridden_component(context, 'ec2', index=node, allowed=['type', 'ext'], interesting=['type'])
        overridden_context['ec2'] = overridden_ec2

        instance = ec2instance(overridden_context, node)
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
    lb = context.get('elb') or context.get('alb')
    # single ec2 node may get an external hostname
    if context['full_hostname'] and not lb:
        ensure(context['ec2']['cluster-size'] <= 1,
               "If there is no load balancer, multiple EC2 instances cannot be assigned a single DNS entry")

        if context['ec2']['cluster-size'] == 1:
            template.add_resource(external_dns_ec2_single(context))
            [template.add_resource(cname) for cname in cnames(context)]
        else:
            # see `render_elb` and `render_alb` for clustered node DNS
            pass

    # single ec2 node may get an internal hostname
    if context['int_full_hostname'] and not lb:
        ensure(context['ec2']['cluster-size'] == 1,
               "If there is no load balancer, only a single EC2 instance can be assigned a DNS entry")
        template.add_resource(internal_dns_ec2_single(context))

    # ec2 nodes in a cluster may get a different internal hostname each
    suppressed = context['ec2'].get('suppressed', [])
    if context['ec2']['dns-internal']:
        for node in range(1, context['ec2']['cluster-size'] + 1):
            if node in suppressed:
                continue

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

    # primary ec2 node in a cluster may get an external hostname
    if context['domain'] and context['ec2']['dns-external-primary']:
        hostedzone = context['domain'] + "."
        primary = 1
        dns_record = route53.RecordSetType(
            R53_EXT_TITLE_NODE % primary,
            HostedZoneName=hostedzone,
            Comment="External DNS record for EC2 primary",
            Name=context['ext_node_hostname'] % primary,
            Type="A",
            TTL="60",
            ResourceRecords=[GetAtt(EC2_TITLE_NODE % primary, "PublicIp")],
        )
        template.add_resource(dns_record)

# --- rds

def rdsdbparams(context, template):
    if not context.get('rds_params'):
        return None
    lu = partial(utils.lu, context)
    engine = lu('rds.engine')
    version = str(lu('rds.version'))
    name = RDS_DB_PG
    dbpg = rds.DBParameterGroup(name, **{
        'Family': "%s%s" % (engine.lower(), version), # "mysql5.6", "postgres9.4"
        'Description': '%s (%s) custom parameters' % (context['project_name'], context['instance_id']),
        'Parameters': context['rds_params']
    })
    template.add_resource(dbpg)
    return Ref(dbpg)

def rds_security(context):
    """returns a security group for an RDS instance.
    This security group only allows access within the subnet, not because of the ip address range but
    because this is dealt with in the subnet configuration"""
    engine_ports = {
        'postgres': 5432,
        'mysql': 3306
    }
    ingress_data = [engine_ports[context['rds']['engine'].lower()]]
    ingress_ports = _convert_ports_to_dictionary(ingress_data)
    return security_group("VPCSecurityGroup",
                          context['aws']['vpc-id'],
                          ingress_ports,
                          "RDS DB security group")

def render_rds(context, template):
    lu = partial(utils.lu, context)

    # db subnet *group*
    # it's expected the db subnets themselves are already created within the VPC
    # you just need to plug their ids into the project file.
    # not really sure if a subnet group is anything more meaningful than 'a collection of subnet ids'
    rsn = rds.DBSubnetGroup(DBSUBNETGROUP_TITLE, **{
        "DBSubnetGroupDescription": "a group of subnets for this rds instance.",
        "SubnetIds": lu('rds.subnets'),
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
        'AllocatedStorage': lu('rds.storage'),
        'StorageType': lu('rds.storage-type'),
        'MultiAZ': lu('rds.multi-az'),
        'VPCSecurityGroups': [Ref(vpcdbsg)],
        'DBSubnetGroupName': Ref(rsn),
        'DBInstanceClass': lu('rds.type'),
        'Engine': lu('rds.engine'),
        # something is converting this value to an int from a float :(
        "EngineVersion": str(lu('rds.version')), # 'defaults.aws.rds.storage')),
        'MasterUsername': lu('rds_username'), # pillar data is now UNavailable
        'MasterUserPassword': lu('rds_password'),
        'BackupRetentionPeriod': lu('rds.backup-retention'),
        'DeletionPolicy': lu('rds.deletion-policy'),
        "Tags": tags,
        "AllowMajorVersionUpgrade": lu('rds.allow-major-version-upgrade'),
        "AutoMinorVersionUpgrade": True, # default
    }

    if param_group_ref:
        data['DBParameterGroupName'] = param_group_ref

    if lu('rds.encryption'):
        data['StorageEncrypted'] = True
        data['KmsKeyId'] = lu('rds.encryption') if isinstance(lu('rds.encryption'), str) else ''

    rdbi = rds.DBInstance(RDS_TITLE, **data)
    lmap(template.add_resource, [rsn, rdbi, vpcdbsg])

    outputs = [
        mkoutput("RDSHost", "Connection endpoint for the DB cluster", (RDS_TITLE, "Endpoint.Address")),
        mkoutput("RDSPort", "The port number on which the database accepts connections", (RDS_TITLE, "Endpoint.Port")),
    ]
    lmap(template.add_output, outputs)

# --- sqs/sns

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

# --- s3

def render_s3(context, template):
    for bucket_name in context['s3']:
        props = {
            'DeletionPolicy': context['s3'][bucket_name]['deletion-policy'].capitalize(),
            'Tags': s3.Tags(**aws.generic_tags(context, name=False)),
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

        if context['s3'][bucket_name]['encryption']:
            props['BucketEncryption'] = _bucket_kms_encryption(context['s3'][bucket_name]['encryption'])

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

def _bucket_kms_encryption(key_arn):
    return s3.BucketEncryption(
        ServerSideEncryptionConfiguration=[
            s3.ServerSideEncryptionRule(
                ServerSideEncryptionByDefault=s3.ServerSideEncryptionByDefault(
                    KMSMasterKeyID=key_arn,
                    SSEAlgorithm='aws:kms'
                )
            )
        ]
    )

# --- elb

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

def elb_tags(context):
    tags = aws.generic_tags(context)
    tags.update({
        'Name': '%s--elb' % context['stackname'], # "journal--prod--elb"
    })
    return [ec2.Tag(key, value) for key, value in tags.items()]

def _elb_healthcheck_target(context):
    if context['elb']['healthcheck']['protocol'] == 'tcp':
        return 'TCP:%d' % context['elb']['healthcheck'].get('port', 80)
    if context['elb']['healthcheck']['protocol'] == 'http':
        return 'HTTP:%s%s' % (context['elb']['healthcheck']['port'], context['elb']['healthcheck']['path'])
    raise ValueError("Unsupported healthcheck protocol: %s" % context['elb']['healthcheck']['protocol'])

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

    protocols = context['elb']['protocol']
    if isstr(protocols):
        protocols = [protocols]

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
        elif isinstance(protocol, int):
            port = protocol
            listeners.append(elb.Listener(
                InstanceProtocol='TCP',
                InstancePort=str(port),
                LoadBalancerPort=str(port),
                PolicyNames=listeners_policy_names,
                Protocol='TCP'
            ))
            elb_ports.append(port)
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
        elb_ports.append(listener['port'])

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

    template.add_output(mkoutput(
        "ElasticLoadBalancer",
        "Generated name of the ELB",
        Ref(ELB_TITLE))
    )

    template.add_resource(security_group(
        SECURITY_GROUP_ELB_TITLE,
        context['aws']['vpc-id'],
        _convert_ports_to_dictionary(elb_ports)
    )) # list of strings or dicts

    if context['full_hostname'] or context['int_full_hostname']:
        dns = external_dns_elb if elb_is_public else internal_dns_elb
        template.add_resource(dns(context))
    if context['full_hostname']:
        [template.add_resource(cname) for cname in cnames(context)]

# --- alb

def _external_dns_alb(context):
    # http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_EXT_TITLE,
        HostedZoneName=hostedzone,
        Comment="External DNS record for ALB",
        Name=context['full_hostname'],
        Type="A",
        AliasTarget=route53.AliasTarget(
            GetAtt(ALB_TITLE, "CanonicalHostedZoneNameID"),
            GetAtt(ALB_TITLE, "DNSName")
        )
    )
    return dns_record

def _internal_dns_alb(context):
    # The DNS name of an existing Amazon Route 53 hosted zone
    hostedzone = context['int_domain'] + "." # TRAILING DOT IS IMPORTANT!
    dns_record = route53.RecordSetType(
        R53_INT_TITLE,
        HostedZoneName=hostedzone,
        Comment="Internal DNS record for ALB",
        Name=context['int_full_hostname'],
        Type="A",
        AliasTarget=route53.AliasTarget(
            GetAtt(ALB_TITLE, "CanonicalHostedZoneNameID"),
            GetAtt(ALB_TITLE, "DNSName")
        )
    )
    return dns_record

def render_alb(context, template, ec2_instances):
    """
    https://troposphere.readthedocs.io/en/latest/apis/troposphere.html#module-troposphere.elasticloadbalancingv2
    """

    # -- load balancer

    lb_attrs = {
        'idle_timeout.timeout_seconds': context['alb']['idle_timeout'],
    }
    lb_attrs = [alb.LoadBalancerAttributes(Key=key, Value=val) for key, val in lb_attrs.items()]

    ALB_SECURITY_GROUP_ID = ALB_TITLE + "SecurityGroup"

    lb = alb.LoadBalancer(
        ALB_TITLE,
        Subnets=context['alb']['subnets'],
        SecurityGroups=[Ref(ALB_SECURITY_GROUP_ID)],
        Type='application', # default, could also be 'network', superceding ELB logic
        # Tags=[], # TODO
        LoadBalancerAttributes=lb_attrs,
    )

    protocol_map = {
        'http': {'protocol': 'HTTP',
                 'port': 80},
        'https': {'protocol': 'HTTPS',
                  'port': 443},
        # not used
        # 'tcp': {'protocol': 'TCP',
        #        'port': str(protocol)}
    }

    # -- target groups, also one for each protocol+port pair

    def healthcheck(protocol):
        if protocol != context['alb']['healthcheck']['protocol']:
            return {}
        return {
            'HealthCheckEnabled': True,
            "HealthCheckIntervalSeconds": context['alb']['healthcheck']['interval'],
            "HealthCheckPath": context['alb']['healthcheck']['path'],
            "HealthCheckPort": context['alb']['healthcheck']['port'],
            "HealthCheckProtocol": context['alb']['healthcheck']['protocol'],
            "HealthCheckTimeoutSeconds": context['alb']['healthcheck']['timeout'],
            "HealthyThresholdCount": context['alb']['healthcheck']['healthy_threshold'],
            "UnhealthyThresholdCount": context['alb']['healthcheck']['unhealthy_threshold'],
        }

    def target_group_id(protocol):
        return ALB_TITLE + 'TargetGroup' + str(protocol).title()

    _lb_target_group_list = []
    for protocol in context['alb']['protocol']:
        _lb_target_group = {
            'Protocol': protocol_map[protocol]['protocol'],
            'Port': protocol_map[protocol]['port'],
            'Targets': [], # TODO
            'VpcId': context['aws']['vpc-id'],
        }
        # if protocol == 'https':
        #    _lb_target_group['ProtocolVersion'] = 'HTTP2'
        _lb_target_group.update(healthcheck(protocol))
        _lb_target_group_list.append(
            alb.TargetGroup(
                # "ElasticLoadBalancerV2TargetGroupHttps"
                target_group_id(protocol),
                **_lb_target_group))

    # -- listeners, one for each protocol+port pair
    #    listeners need to know about target groups

    _lb_listener_list = []
    for protocol in context['alb']['protocol']:
        _lb_listener_action = alb.Action(
            Type='forward', # or 'redirect' ? not sure
            TargetGroupArn=GetAtt(target_group_id(protocol), 'Arn')
        )
        _lb_listener_list.append(alb.Listener(
            # "ElasticLoadBalancerV2ListenerHttps"
            ALB_TITLE + 'Listener' + str(protocol).title(),
            LoadBalancerArn=GetAtt(lb, 'Arn'),
            DefaultActions=[_lb_listener_action],
            Port=protocol_map[protocol]['port'],
            Protocol=protocol_map[protocol]['protocol']
        ))

    # -- security group

    alb_ports = [protocol_map[protocol]['port'] for protocol in context['alb']['protocol']]
    alb_ports = _convert_ports_to_dictionary(alb_ports)
    _lb_security_group = security_group(
        ALB_SECURITY_GROUP_ID,
        context['aws']['vpc-id'],
        alb_ports
    )

    # -- dns

    alb_is_public = True if context['full_hostname'] else False
    if context['full_hostname'] or context['int_full_hostname']:
        dns = _external_dns_alb if alb_is_public else _internal_dns_alb
        template.add_resource(dns(context))

    if context['full_hostname']:
        [template.add_resource(cname) for cname in cnames(context)]

    # ---

    resources = [lb, _lb_security_group]
    resources.extend(_lb_listener_list)
    resources.extend(_lb_target_group_list)
    [template.add_resource(resource) for resource in resources]

    # --- outputs (TODO)

    return context

# --- cloudfront

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
                CustomOriginConfig=cloudfront.CustomOriginConfig(
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
                CustomOriginConfig=cloudfront.CustomOriginConfig(
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
            CustomOriginConfig=cloudfront.CustomOriginConfig(
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


# --- fastly

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


def render_fastly(context, template):
    "WARNING: only creates Route53 DNS entries, delegating the rest of the setup to Terraform"
    for dns in external_dns_fastly(context):
        template.add_resource(dns)

# --- elasticache

def elasticache_security_group(context):
    "returns a security group for the ElastiCache instances. this security group only allows access within the VPC"
    engine_ports = {
        'redis': 6379,
    }
    ingress_data = [engine_ports[context['elasticache']['engine']]]
    ingress_ports = _convert_ports_to_dictionary(ingress_data)
    return security_group(ELASTICACHE_SECURITY_GROUP_TITLE,
                          context['aws']['vpc-id'],
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

        cluster_context = overridden_component(context, 'elasticache', index=cluster, allowed=['type', 'version', 'az', 'configuration'])

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
            Tags=Tags(**aws.generic_tags(context)),
            VpcSecurityGroupIds=[Ref(cache_security_group)],
        ))

        outputs = [
            mkoutput("ElastiCacheHost%s" % cluster, "The hostname on which the cache accepts connections", (cluster_title, "RedisEndpoint.Address")),
            mkoutput("ElastiCachePort%s" % cluster, "The port number on which the cache accepts connections", (cluster_title, "RedisEndpoint.Port")),
        ]
        lmap(template.add_output, outputs)

    if default_parameter_group_use:
        template.add_resource(parameter_group)

# --- docdb

def docdb_security(context):
    """returns a security group for a DocumentDB instance.
    This security group only allows access within the subnet, not because of the ip address range but
    because this is dealt with in the subnet configuration"""
    ingress_data = [27017] # default MongoDB port
    ingress_ports = _convert_ports_to_dictionary(ingress_data)
    return security_group("DocumentDBSecurityGroup",
                          context['aws']['vpc-id'],
                          ingress_ports,
                          "DocumentDB security group")

def render_docdb(context, template):
    # create cluster
    subnet_group = docdb.DBSubnetGroup('DocumentDBSubnet', **{
        "DBSubnetGroupDescription": "a group of subnets for this DocumentDB cluster.",
        "SubnetIds": context['docdb']['subnets']
    })

    docdb_security_group = docdb_security(context)

    cluster = {
        'title': 'DocumentDBCluster', # resource name
        'BackupRetentionPeriod': context['docdb']['backup-retention-period'],
        'DeletionProtection': context['docdb']['deletion-protection'],
        'MasterUserPassword': context['docdb']['master-user-password'],
        'MasterUsername': context['docdb']['master-username'],
        'Tags': instance_tags(context, single_tag_obj=True),
        'StorageEncrypted': context['docdb']['storage-encrypted'],
        'VpcSecurityGroupIds': [Ref(docdb_security_group)],
        'DBSubnetGroupName': Ref(subnet_group),
        'EngineVersion': context['docdb']['engine-version'],
    }
    _remove_if_none(cluster, ['BackupRetentionPeriod'])
    cluster = docdb.DBCluster(**cluster)
    [template.add_resource(r) for r in [subnet_group, docdb_security_group, cluster]]

    # create nodes
    def docdb_node(node):
        return docdb.DBInstance(**{
            'title': 'DocumentDBInst%d' % node,
            'DBClusterIdentifier': Ref(cluster),
            'AutoMinorVersionUpgrade': context['docdb']['minor-version-upgrades'],
            'DBInstanceClass': context['docdb']['type'],
            'Tags': instance_tags(context, node, single_tag_obj=True),
        })
    for i in range(1, context['docdb']['cluster-size'] + 1):
        template.add_resource(docdb_node(i))

# --- todo: revisit this, seems to be part of rds+ec2

def add_outputs(context, template):
    if R53_EXT_TITLE in template.resources.keys():
        template.add_output(mkoutput("DomainName", "Domain name of the newly created stack instance", Ref(R53_EXT_TITLE)))

    if R53_INT_TITLE in template.resources.keys():
        template.add_output(mkoutput("IntDomainName", "Domain name of the newly created stack instance", Ref(R53_INT_TITLE)))

#
#
#

def render(context):
    template = Template()

    ec2_instances = render_ec2(context, template) if context['ec2'] else {}
    cluster_size = context['ec2']['cluster-size'] if context['ec2'] else 0

    # order is possibly important as each render function is modifying
    # the state of a single `Template` object.
    renderer_list = [
        # ('ec2', render_ec2), # called above. other renderers depend on it's result
        ('rds', render_rds),
        ('ext', render_ext, {'cluster_size': cluster_size, 'actual_ec2_instances': ec2_instances.keys()}),
        ('sns', render_sns),
        ('sqs', render_sqs),
        ('s3', render_s3),

        # hostname is assigned to an ELB, which has priority over
        # N>=1 EC2 instances
        ('elb', render_elb, {'ec2_instances': ec2_instances}),
        ('alb', render_alb, {'ec2_instances': ec2_instances}),
        ('ec2', render_ec2_dns),
        ('cloudfront', render_cloudfront, {'origin_hostname': context['full_hostname']}),
        ('fastly', render_fastly),
        ('elasticache', render_elasticache),
        ('docdb', render_docdb),
    ]

    for value in renderer_list:
        context_key, render_fn = value[0], value[1]
        kwargs = value[2] if len(value) == 3 else {}
        if context[context_key]: # "if 's3' in context, then render_s3(...)"
            render_fn(context, template, **kwargs)

    # todo: needs some attention.
    add_outputs(context, template)

    return template.to_json()
