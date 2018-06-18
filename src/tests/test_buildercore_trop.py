from collections import OrderedDict
import json  # , yaml
import os
from os.path import join
from . import base
from buildercore import cfngen, trop

class TestBuildercoreTrop(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')
        os.environ['LOGNAME'] = 'my_user'

    def tearDown(self):
        del os.environ['LOGNAME']

    def _parse_json(self, dump):
        """Parses dump into a dictionary, using strings rather than unicode strings

        Ridiculously, the yaml module is more helpful in parsing JSON than the json module. Using json.loads() will result in unhelpful error messages like
        -  'Type': 'AWS::Route53::RecordSet'}
        +  u'Type': u'AWS::Route53::RecordSet'}
        that hide the true comparison problem in self.assertEquals().
        """
        # return yaml.safe_load(dump) # slightly improved in python3?
        return json.loads(dump)

    def test_rds_template_contains_rds(self):
        extra = {
            'stackname': 'dummy3--test',
            'alt-config': 'alt-config1'
        }
        context = cfngen.build_context('dummy3', **extra)
        self.assertEqual(context['rds_dbname'], "dummy3test")
        self.assertEqual(context['rds_instance_id'], "dummy3-test")
        data = self._parse_json(trop.render(context))
        self.assertTrue(isinstance(data['Resources']['AttachedDB'], dict))
        # "Test that sequence first contains the same elements as second, regardless of their order."
        self.assertCountEqual(
            data['Resources']['AttachedDB']['Properties']['Tags'],
            [
                {'Key': 'Project', 'Value': 'dummy3'},
                {'Key': 'Environment', 'Value': 'test'},
                {'Key': 'Name', 'Value': 'dummy3--test'},
                {'Key': 'Cluster', 'Value': 'dummy3--test'},
            ]
        )

    def test_rds_param_groups(self):
        extra = {
            'stackname': 'project-with-db-params--1',
        }
        context = cfngen.build_context('project-with-db-params', **extra)
        expected_params = {'key1': 'val1', 'key2': 'val2'}
        # params are read in from project file
        self.assertEqual(context['rds_params'], expected_params)
        # rendered template has a db parameter group attached to it
        cfntemplate = json.loads(trop.render(context))
        expected = {
            "Type": "AWS::RDS::DBParameterGroup",
            "Properties": {
                "Description": "project-with-db-params (1) custom parameters",
                "Family": "postgres9.4",
                "Parameters": {
                    "key1": "val1",
                    "key2": "val2",
                }
            }
        }
        self.assertEqual(cfntemplate['Resources']['RDSDBParameterGroup'], expected)

    def test_sns_template(self):
        extra = {
            'stackname': 'just-some-sns--prod',
        }
        context = cfngen.build_context('just-some-sns', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertEqual(['WidgetsProdTopic'], list(data['Resources'].keys()))
        self.assertEqual(
            {'Type': 'AWS::SNS::Topic', 'Properties': {'TopicName': 'widgets-prod'}},
            data['Resources']['WidgetsProdTopic']
        )
        self.assertEqual(['WidgetsProdTopicArn'], list(data['Outputs'].keys()))
        self.assertEqual(
            {'Value': {'Ref': 'WidgetsProdTopic'}},
            data['Outputs']['WidgetsProdTopicArn']
        )

    def test_sqs_template(self):
        extra = {
            'stackname': 'project-with-sqs--prod',
        }
        context = cfngen.build_context('project-with-sqs', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertEqual(['ProjectWithSqsIncomingProdQueue'], list(data['Resources'].keys()))
        self.assertEqual(
            {'Type': 'AWS::SQS::Queue', 'Properties': {'QueueName': 'project-with-sqs-incoming-prod'}},
            data['Resources']['ProjectWithSqsIncomingProdQueue']
        )
        self.assertEqual(['ProjectWithSqsIncomingProdQueueArn'], list(data['Outputs'].keys()))
        self.assertEqual(
            {'Value': {'Fn::GetAtt': ['ProjectWithSqsIncomingProdQueue', 'Arn']}},
            data['Outputs']['ProjectWithSqsIncomingProdQueueArn']
        )

    def test_ext_template(self):
        extra = {
            'stackname': 'project-with-ext--prod',
        }
        context = cfngen.build_context('project-with-ext', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertIn('MountPoint1', list(data['Resources'].keys()))
        self.assertIn('ExtraStorage1', list(data['Resources'].keys()))
        self.assertCountEqual(
            {
                'AvailabilityZone': {'Fn::GetAtt': ['EC2Instance1', 'AvailabilityZone']},
                'VolumeType': 'standard',
                'Size': '200',
                'Tags': [
                    {'Key': 'Project', 'Value': 'project-with-ext'},
                    {'Key': 'Environment', 'Value': 'prod'},
                    {'Key': 'Name', 'Value': 'project-with-ext--prod--1'},
                    {'Key': 'Cluster', 'Value': 'project-with-ext--prod'},
                    {'Key': 'Node', 'Value': '1'},
                ],
            },
            data['Resources']['ExtraStorage1']['Properties']
        )
        self.assertEqual(
            {
                'Device': '/dev/sdh',
                'InstanceId': {'Ref': 'EC2Instance1'},
                'VolumeId': {'Ref': 'ExtraStorage1'},
            },
            data['Resources']['MountPoint1']['Properties']
        )

    def test_root_volume_size_template(self):
        extra = {
            'stackname': 'project-with-ec2-custom-root--prod',
        }
        context = cfngen.build_context('project-with-ec2-custom-root', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        ec2 = data['Resources']['EC2Instance1']['Properties']
        self.assertIn('BlockDeviceMappings', ec2)
        self.assertEqual(
            ec2['BlockDeviceMappings'],
            [
                {
                    'DeviceName': '/dev/sda1',
                    'Ebs': {
                        'VolumeSize': 20,
                        'VolumeType': 'standard',
                    },
                },
            ]
        )

    def test_clustered_template(self):
        extra = {
            'stackname': 'project-with-cluster--prod',
        }
        context = cfngen.build_context('project-with-cluster', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertIn('EC2Instance1', list(resources.keys()))
        self.assertIn('EC2Instance2', list(resources.keys()))
        self.assertIn('StackSecurityGroup', list(resources.keys()))

        # different subnets, placed in different Availability Zones
        self.assertEqual(resources['EC2Instance1']['Properties']['SubnetId'], 'subnet-1d4eb46a')
        self.assertEqual(resources['EC2Instance2']['Properties']['SubnetId'], 'subnet-7a31dd46')

        self.assertIn(
            {
                'Key': 'Name',
                'Value': 'project-with-cluster--prod--1',
            },
            resources['EC2Instance1']['Properties']['Tags']
        )
        self.assertIn(
            {
                'Key': 'Environment',
                'Value': 'prod',
            },
            resources['EC2Instance1']['Properties']['Tags']
        )
        self.assertIn(
            {
                'Key': 'Cluster',
                'Value': 'project-with-cluster--prod',
            },
            resources['EC2Instance1']['Properties']['Tags']
        )
        outputs = data['Outputs']
        self.assertIn('InstanceId1', list(outputs.keys()))
        self.assertEqual({'Ref': 'EC2Instance1'}, outputs['InstanceId1']['Value'])
        self.assertEqual({'Ref': 'EC2Instance1'}, outputs['InstanceId1']['Value'])
        self.assertIn('ElasticLoadBalancer', list(resources.keys()))
        elb = resources['ElasticLoadBalancer']['Properties']
        self.assertEqual(elb['Scheme'], 'internet-facing')
        self.assertEqual(1, len(elb['Listeners']))
        self.assertEqual(
            elb['Instances'],
            [
                {
                    'Ref': 'EC2Instance1',
                },
                {
                    'Ref': 'EC2Instance2',
                }
            ]
        )
        self.assertEqual(
            elb['Listeners'][0],
            {
                'InstancePort': '80',
                'InstanceProtocol': 'HTTP',
                'LoadBalancerPort': '80',
                'PolicyNames': [],
                'Protocol': 'HTTP',
            }
        )
        self.assertEqual(
            elb['HealthCheck'],
            {
                'Target': 'HTTP:80/ping',
                'Timeout': '4',
                'Interval': '5',
                'HealthyThreshold': '2',
                'UnhealthyThreshold': '2',
            }
        )
        self.assertIn(
            {
                'Key': 'Name',
                'Value': 'project-with-cluster--prod--elb',
            },
            resources['ElasticLoadBalancer']['Properties']['Tags']
        )
        self.assertIn(
            {
                'Key': 'Cluster',
                'Value': 'project-with-cluster--prod',
            },
            resources['ElasticLoadBalancer']['Properties']['Tags']
        )
        self.assertNotIn('IntDNS', list(resources.keys()))
        dns = resources['ExtDNS']['Properties']
        self.assertIn('AliasTarget', list(dns.keys()))
        self.assertEqual(dns['Name'], 'prod--project-with-cluster.example.org')
        self.assertIn('DomainName', list(outputs.keys()))
        self.assertIn('CnameDNS1', list(resources.keys()))
        self.assertEqual(
            {
                'AliasTarget': {
                    'DNSName': {
                        'Fn::GetAtt': ['ElasticLoadBalancer', 'DNSName']
                    },
                    'HostedZoneId': {'Fn::GetAtt': ['ElasticLoadBalancer', 'CanonicalHostedZoneNameID']}
                },
                'HostedZoneName': 'project.tv.',
                'Name': 'project.tv',
                'Type': 'A'
            },
            resources['CnameDNS1']['Properties']
        )
        self.assertIn('CnameDNS2', list(resources.keys()))
        self.assertEqual(
            {
                'AliasTarget': {
                    'DNSName': {
                        'Fn::GetAtt': ['ElasticLoadBalancer', 'DNSName']
                    },
                    'HostedZoneId': {'Fn::GetAtt': ['ElasticLoadBalancer', 'CanonicalHostedZoneNameID']}
                },
                'HostedZoneName': 'example.org.',
                'Name': 'example.org',
                'Type': 'A'
            },
            resources['CnameDNS2']['Properties']
        )

        self.assertIn('IntDNS1', list(resources.keys()))
        self.assertEqual(
            {
                'ResourceRecords': [{'Fn::GetAtt': ['EC2Instance1', 'PrivateIp']}],
                'HostedZoneName': 'example.internal.',
                'Name': 'prod--project-with-cluster--1.example.internal',
                'TTL': '60',
                'Type': 'A',
                'Comment': 'Internal DNS record for EC2 node 1',
            },
            resources['IntDNS1']['Properties']
        )
        self.assertIn('IntDNS2', list(resources.keys()))

    def test_clustered_template_suppressing_some_nodes(self):
        extra = {
            'stackname': 'project-with-cluster-suppressed--prod',
        }
        context = cfngen.build_context('project-with-cluster-suppressed', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertNotIn('EC2Instance1', list(resources.keys()))
        self.assertIn('EC2Instance2', list(resources.keys()))
        self.assertIn('EC2Instance3', list(resources.keys()))
        self.assertNotIn('ExtraStorage1', list(resources.keys()))
        self.assertIn('ExtraStorage2', list(resources.keys()))
        self.assertIn('ExtraStorage3', list(resources.keys()))

        self.assertIn('ElasticLoadBalancer', list(resources.keys()))
        elb = resources['ElasticLoadBalancer']['Properties']
        self.assertEqual(
            elb['Instances'],
            [
                {
                    'Ref': 'EC2Instance2',
                },
                {
                    'Ref': 'EC2Instance3',
                }
            ]
        )

    def test_clustered_template_empty(self):
        extra = {
            'stackname': 'project-with-cluster-empty--prod',
        }
        context = cfngen.build_context('project-with-cluster-empty', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertEqual(resources.keys(), ['StackSecurityGroup'])
        security_group = resources['StackSecurityGroup']['Properties']
        self.assertEqual(
            security_group,
            {
                'GroupDescription': 'security group',
                'SecurityGroupIngress': [{
                    'CidrIp': '0.0.0.0/0',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpProtocol': 'tcp',
                }],
                'VpcId': 'vpc-78a2071d',
            }
        )

    def test_clustered_template_with_node_overrides(self):
        extra = {
            'stackname': 'project-with-cluster-overrides--prod',
        }
        context = cfngen.build_context('project-with-cluster-overrides', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertIn('EC2Instance1', list(resources.keys()))
        self.assertIn('EC2Instance2', list(resources.keys()))
        self.assertIn('ExtraStorage1', list(resources.keys()))
        self.assertIn('ExtraStorage2', list(resources.keys()))
        self.assertEqual(
            resources['ExtraStorage1']['Properties']['Size'],
            '20'
        )
        self.assertEqual(
            resources['ExtraStorage2']['Properties']['Size'],
            '10'
        )

    def test_multiple_elb_listeners(self):
        extra = {
            'stackname': 'project-with-multiple-elb-listeners--prod',
        }
        context = cfngen.build_context('project-with-multiple-elb-listeners', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertIn('ElasticLoadBalancer', list(resources.keys()))
        elb = resources['ElasticLoadBalancer']['Properties']
        listeners = elb['Listeners']
        self.assertEqual(
            listeners,
            [
                {
                    'InstancePort': '80',
                    'InstanceProtocol': 'HTTP',
                    'LoadBalancerPort': '80',
                    'PolicyNames': [],
                    'Protocol': 'HTTP',
                },
                {
                    'InstancePort': '8001',
                    'InstanceProtocol': 'HTTP',
                    'LoadBalancerPort': '8001',
                    'PolicyNames': [],
                    'Protocol': 'HTTPS',
                    'SSLCertificateId': 'arn:aws:iam::...:...',
                },
            ]
        )
        self.assertIn('ELBSecurityGroup', list(resources.keys()))
        elb_security_group_ingress = resources['ELBSecurityGroup']['Properties']['SecurityGroupIngress']
        self.assertEqual(
            [
                {
                    'ToPort': 80,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 8001,
                    'FromPort': 8001,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ],
            elb_security_group_ingress
        )

        stack_security_group_ingress = resources['StackSecurityGroup']['Properties']['SecurityGroupIngress']
        self.assertEqual(
            [
                {
                    'ToPort': 80,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 8001,
                    'FromPort': 8001,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ],
            stack_security_group_ingress
        )

    def test_additional_cnames(self):
        extra = {
            'stackname': 'dummy2--prod',
        }
        context = cfngen.build_context('dummy2', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertIn('CnameDNS1', list(resources.keys()))
        dns = resources['CnameDNS1']['Properties']
        self.assertEqual(
            dns,
            {
                'HostedZoneName': 'example.org.',
                'Name': 'official.example.org',
                'ResourceRecords': ['prod--dummy2.example.org'],
                'TTL': '60',
                'Type': 'CNAME',
            }
        )

    def test_stickiness_template(self):
        extra = {
            'stackname': 'project-with-stickiness--prod',
        }
        context = cfngen.build_context('project-with-stickiness', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        resources = data['Resources']
        self.assertIn('ElasticLoadBalancer', list(resources.keys()))
        elb = resources['ElasticLoadBalancer']['Properties']
        self.assertEqual(
            elb['AppCookieStickinessPolicy'],
            [
                {
                    'CookieName': 'mysessionid',
                    'PolicyName': 'AppCookieStickinessPolicy',
                }
            ]
        )
        self.assertEqual(
            elb['Listeners'][0]['PolicyNames'],
            [
                'AppCookieStickinessPolicy',
            ]
        )

    def test_s3_template(self):
        extra = {
            'stackname': 'project-with-s3--prod',
        }
        context = cfngen.build_context('project-with-s3', **extra)
        self.assertEqual(
            {
                'sqs-notifications': {},
                'deletion-policy': 'delete',
                'website-configuration': None,
                'cors': None,
                'public': False,
            },
            context['s3']['widgets-prod']
        )
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('WidgetsProdBucket' in list(data['Resources'].keys()))
        self.assertTrue('WidgetsArchiveProdBucket' in list(data['Resources'].keys()))
        self.assertTrue('WidgetsStaticHostingProdBucket' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'Type': 'AWS::S3::Bucket',
                'DeletionPolicy': 'Delete',
                'Properties': {
                    'BucketName': 'widgets-prod',
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Environment', 'Value': 'prod'},
                        {'Key': 'Name', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Project', 'Value': 'project-with-s3'},
                    ],
                }
            },
            data['Resources']['WidgetsProdBucket']
        )
        self.assertEqual(
            {
                'Type': 'AWS::S3::Bucket',
                'DeletionPolicy': 'Retain',
                'Properties': {
                    'BucketName': 'widgets-archive-prod',
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Environment', 'Value': 'prod'},
                        {'Key': 'Name', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Project', 'Value': 'project-with-s3'},
                    ],
                },
            },
            data['Resources']['WidgetsArchiveProdBucket']
        )
        self.assertEqual(
            {
                'Type': 'AWS::S3::Bucket',
                'DeletionPolicy': 'Delete',
                'Properties': {
                    'BucketName': 'widgets-static-hosting-prod',
                    'CorsConfiguration': {
                        'CorsRules': [
                            {
                                'AllowedHeaders': ['*'],
                                'AllowedMethods': ['GET', 'HEAD'],
                                'AllowedOrigins': ['*'],
                            },
                        ],
                    },
                    'WebsiteConfiguration': {
                        'IndexDocument': 'index.html',
                    },
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Environment', 'Value': 'prod'},
                        {'Key': 'Name', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Project', 'Value': 'project-with-s3'},
                    ],
                },
            },
            data['Resources']['WidgetsStaticHostingProdBucket']
        )

        self.assertEqual(
            {
                'Type': 'AWS::S3::BucketPolicy',
                'Properties': {
                    'Bucket': 'widgets-static-hosting-prod',
                    'PolicyDocument': {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Sid": "AddPerm",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["s3:GetObject"],
                            "Resource":[
                                "arn:aws:s3:::widgets-static-hosting-prod/*",
                            ]
                        }]
                    }
                },
            },
            data['Resources']['WidgetsStaticHostingProdBucketPolicy']
        )

        self.assertEqual(
            {
                'Type': 'AWS::S3::Bucket',
                'DeletionPolicy': 'Delete',
                'Properties': {
                    'AccessControl': 'PublicRead',
                    'BucketName': 'widgets-just-access-prod',
                    'Tags': [
                        {'Key': 'Cluster', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Environment', 'Value': 'prod'},
                        {'Key': 'Name', 'Value': 'project-with-s3--prod'},
                        {'Key': 'Project', 'Value': 'project-with-s3'},
                    ],
                },
            },
            data['Resources']['WidgetsJustAccessProdBucket']
        )

        self.assertEqual(
            {
                'Type': 'AWS::S3::BucketPolicy',
                'Properties': {
                    'Bucket': 'widgets-just-access-prod',
                    'PolicyDocument': {
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Sid": "AddPerm",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["s3:GetObject"],
                            "Resource":[
                                "arn:aws:s3:::widgets-just-access-prod/*",
                            ]
                        }]
                    }
                },
            },
            data['Resources']['WidgetsJustAccessProdBucketPolicy']
        )

    def test_cdn_template(self):
        extra = {
            'stackname': 'project-with-cloudfront--prod',
        }
        context = cfngen.build_context('project-with-cloudfront', **extra)
        self.assertEqual(
            {
                'certificate_id': 'dummy...',
                'compress': True,
                'cookies': ['session_id'],
                'headers': ['Accept'],
                'logging': {
                    'bucket': 'acme-logs',
                },
                'origins': {},
                'subdomains': ['prod--cdn-of-www.example.org', 'example.org'],
                'subdomains-without-dns': ['future.example.org'],
                'errors': None,
                'default-ttl': 5,
            },
            context['cloudfront']
        )
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('CloudFrontCDN' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'Type': 'AWS::CloudFront::Distribution',
                'Properties': {
                    'DistributionConfig': {
                        'Aliases': ['prod--cdn-of-www.example.org', 'example.org', 'future.example.org'],
                        'CacheBehaviors': [],
                        'DefaultCacheBehavior': {
                            'AllowedMethods': ['DELETE', 'GET', 'HEAD', 'OPTIONS', 'PATCH', 'POST', 'PUT'],
                            'CachedMethods': ['GET', 'HEAD'],
                            'Compress': 'true',
                            'DefaultTTL': 5,
                            'ForwardedValues': {
                                'Cookies': {
                                    'Forward': 'whitelist',
                                    'WhitelistedNames': ['session_id'],
                                },
                                'Headers': ['Accept'],
                                # yes this is a string containing the word 'true'...
                                'QueryString': "true",
                            },
                            'TargetOriginId': 'CloudFrontCDNOrigin',
                            'ViewerProtocolPolicy': 'redirect-to-https',
                        },
                        # yes this is a string containing the word 'true'...
                        'Enabled': 'true',
                        'HttpVersion': 'http2',
                        'Logging': {
                            'Bucket': 'acme-logs.s3.amazonaws.com',
                            'Prefix': 'project-with-cloudfront--prod/',
                        },
                        'Origins': [
                            {
                                'DomainName': 'prod--www.example.org',
                                'Id': 'CloudFrontCDNOrigin',
                                'CustomOriginConfig': {
                                    'HTTPSPort': 443,
                                    'OriginProtocolPolicy': 'https-only',
                                },
                            }
                        ],
                        'ViewerCertificate': {
                            'IamCertificateId': 'dummy...',
                            'SslSupportMethod': 'sni-only',
                        },
                    },
                },
            },
            data['Resources']['CloudFrontCDN']
        )
        self.assertTrue('CloudFrontCDNDNS1' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'Type': 'AWS::Route53::RecordSet',
                'Properties': {
                    'AliasTarget': {
                        'DNSName': {
                            'Fn::GetAtt': ['CloudFrontCDN', 'DomainName']
                        },
                        'HostedZoneId': 'Z2FDTNDATAQYW2',
                    },
                    'Comment': 'External DNS record for Cloudfront distribution',
                    'HostedZoneName': 'example.org.',
                    'Name': 'prod--cdn-of-www.example.org.',
                    'Type': 'A',
                },
            },
            data['Resources']['CloudFrontCDNDNS1']
        )
        self.assertTrue('CloudFrontCDNDNS2' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'Type': 'AWS::Route53::RecordSet',
                'Properties': {
                    'AliasTarget': {
                        'DNSName': {
                            'Fn::GetAtt': ['CloudFrontCDN', 'DomainName']
                        },
                        'HostedZoneId': 'Z2FDTNDATAQYW2',
                    },
                    'Comment': 'External DNS record for Cloudfront distribution',
                    'HostedZoneName': 'example.org.',
                    'Name': 'example.org.',
                    'Type': 'A',
                },
            },
            data['Resources']['CloudFrontCDNDNS2']
        )

    def test_cdn_template_minimal(self):
        extra = {
            'stackname': 'project-with-cloudfront-minimal--prod',
        }
        context = cfngen.build_context('project-with-cloudfront-minimal', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('CloudFrontCDN' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'Forward': 'none',
            },
            data['Resources']['CloudFrontCDN']['Properties']['DistributionConfig']['DefaultCacheBehavior']['ForwardedValues']['Cookies']
        )

    def test_cdn_template_multiple_origins(self):
        extra = {
            'stackname': 'project-with-cloudfront-origins--prod',
        }
        context = cfngen.build_context('project-with-cloudfront-origins', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('CloudFrontCDN' in list(data['Resources'].keys()))
        distribution_config = data['Resources']['CloudFrontCDN']['Properties']['DistributionConfig']
        self.assertEqual(
            ['prod--cdn.example.org'],
            distribution_config['Aliases']
        )
        self.assertEqual(
            [
                {
                    'CustomOriginConfig': {
                        'HTTPSPort': 443,
                        'OriginProtocolPolicy': 'https-only',
                    },
                    'DomainName': 'prod--default-bucket.s3.amazonaws.com',
                    'Id': 'default-bucket',
                },
                {
                    'CustomOriginConfig': {
                        'HTTPSPort': 443,
                        'OriginProtocolPolicy': 'https-only',
                    },
                    'DomainName': 'prod--some-bucket.s3.amazonaws.com',
                    'Id': 'some-bucket',
                }
            ],
            distribution_config['Origins']
        )
        self.assertEqual(
            'default-bucket',
            distribution_config['DefaultCacheBehavior']['TargetOriginId'],
        )
        self.assertEqual(1, len(distribution_config['CacheBehaviors']))
        self.assertEqual(
            'some-bucket',
            distribution_config['CacheBehaviors'][0]['TargetOriginId'],
        )
        self.assertEqual(
            'articles/*',
            distribution_config['CacheBehaviors'][0]['PathPattern'],
        )
        self.assertEqual(
            {
                'Cookies': {
                    'Forward': 'whitelist',
                    'WhitelistedNames': ['session_id'],
                },
                'Headers': ['Referer'],
                'QueryString': 'false',
            },
            distribution_config['CacheBehaviors'][0]['ForwardedValues'],
        )

    def test_cdn_template_error_pages(self):
        extra = {
            'stackname': 'project-with-cloudfront-error-pages--prod',
        }
        context = cfngen.build_context('project-with-cloudfront-error-pages', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('CloudFrontCDN' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'CustomOriginConfig': {
                    'HTTPSPort': 443,
                    'OriginProtocolPolicy': 'http-only',
                },
                'DomainName': 'prod--example-errors.com',
                'Id': 'ErrorsOrigin',
            },
            data['Resources']['CloudFrontCDN']['Properties']['DistributionConfig']['Origins'][1]
        )
        self.assertEqual(
            [{
                'DefaultTTL': 300,
                'ForwardedValues': {
                    'Cookies': {
                        'Forward': 'none',
                    },
                    'Headers': [],
                    # yes this is a string containing the word 'false'...
                    'QueryString': 'false',
                },
                'PathPattern': '???.html',
                'TargetOriginId': 'ErrorsOrigin',
                'ViewerProtocolPolicy': 'allow-all',
            }],
            data['Resources']['CloudFrontCDN']['Properties']['DistributionConfig']['CacheBehaviors']
        )
        self.assertEqual(
            [
                {
                    'ErrorCode': 502,
                    'ResponseCode': 502,
                    'ResponsePagePath': '/5xx.html'
                },
            ],
            data['Resources']['CloudFrontCDN']['Properties']['DistributionConfig']['CustomErrorResponses']
        )

    def test_fastly_template_contains_only_dns(self):
        extra = {
            'stackname': 'project-with-fastly-complex--prod',
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertTrue('FastlyDNS1' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'HostedZoneName': 'example.org.',
                'Name': 'prod--cdn1-of-www.example.org',
                'ResourceRecords': ['something.fastly.net'],
                'TTL': '60',
                'Type': 'CNAME',
            },
            data['Resources']['FastlyDNS1']['Properties']
        )

        self.assertTrue('FastlyDNS2' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'HostedZoneName': 'example.org.',
                'Name': 'prod--cdn2-of-www.example.org',
                'ResourceRecords': ['something.fastly.net'],
                'TTL': '60',
                'Type': 'CNAME',
            },
            data['Resources']['FastlyDNS2']['Properties']
        )

        self.assertTrue('FastlyDNS3' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'HostedZoneName': 'example.org.',
                'Name': 'example.org',
                'ResourceRecords': ['127.0.0.1', '127.0.0.2'],
                'TTL': '60',
                'Type': 'A',
            },
            data['Resources']['FastlyDNS3']['Properties']
        )

        self.assertTrue('FastlyDNS4' in list(data['Resources'].keys()))
        self.assertEqual(
            {
                'HostedZoneName': 'anotherdomain.org.',
                'Name': 'anotherdomain.org',
                'ResourceRecords': ['127.0.0.1', '127.0.0.2'],
                'TTL': '60',
                'Type': 'A',
            },
            data['Resources']['FastlyDNS4']['Properties']
        )

    def test_elasticache_redis_template(self):
        extra = {
            'stackname': 'project-with-elasticache-redis--prod',
        }
        context = cfngen.build_context('project-with-elasticache-redis', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertIn('ElastiCache1', list(data['Resources'].keys()))
        self.assertIn('ElastiCacheParameterGroup', list(data['Resources'].keys()))
        self.assertIn('ElastiCacheSecurityGroup', list(data['Resources'].keys()))
        self.assertIn('ElastiCacheSubnetGroup', list(data['Resources'].keys()))
        self.assertEqual(
            {
                'CacheNodeType': 'cache.t2.small',
                'CacheParameterGroupName': {'Ref': 'ElastiCacheParameterGroup'},
                'CacheSubnetGroupName': {'Ref': 'ElastiCacheSubnetGroup'},
                'Engine': 'redis',
                'EngineVersion': '2.8.24',
                'PreferredAvailabilityZone': 'us-east-1a',
                'NumCacheNodes': 1,
                'Tags': [
                    {'Key': 'Cluster', 'Value': 'project-with-elasticache-redis--prod'},
                    {'Key': 'Environment', 'Value': 'prod'},
                    {'Key': 'Name', 'Value': 'project-with-elasticache-redis--prod'},
                    {'Key': 'Project', 'Value': 'project-with-elasticache-redis'},
                ],
                'VpcSecurityGroupIds': [{'Ref': 'ElastiCacheSecurityGroup'}],
            },
            data['Resources']['ElastiCache1']['Properties']
        )
        self.assertEqual(
            {
                'CacheParameterGroupFamily': 'redis2.8',
                'Description': 'ElastiCache parameter group for project-with-elasticache-redis--prod',
                'Properties': {
                    'maxmemory-policy': 'volatile-ttl',
                },
            },
            data['Resources']['ElastiCacheParameterGroup']['Properties']
        )
        self.assertEqual(
            {
                'GroupDescription': 'ElastiCache security group',
                'SecurityGroupIngress': [{
                    # access is dealt with at the subnet level
                    'CidrIp': '0.0.0.0/0',
                    'FromPort': 6379,
                    'IpProtocol': 'tcp',
                    'ToPort': 6379,
                }],
                'VpcId': 'vpc-78a2071d',
            },
            data['Resources']['ElastiCacheSecurityGroup']['Properties']
        )
        self.assertEqual(
            {
                'Description': 'a group of subnets for this cache instance.',
                'SubnetIds': ['subnet-foo', 'subnet-bar'],
            },
            data['Resources']['ElastiCacheSubnetGroup']['Properties']
        )
        self.assertIn('ElastiCacheHost1', data['Outputs'])
        self.assertEqual(
            {
                'Description': 'The hostname on which the cache accepts connections',
                'Value': {'Fn::GetAtt': ['ElastiCache1', 'RedisEndpoint.Address']}
            },
            data['Outputs']['ElastiCacheHost1']
        )
        self.assertIn('ElastiCachePort1', data['Outputs'])
        self.assertEqual(
            {
                'Description': 'The port number on which the cache accepts connections',
                'Value': {'Fn::GetAtt': ['ElastiCache1', 'RedisEndpoint.Port']}
            },
            data['Outputs']['ElastiCachePort1']
        )

    def test_multiple_elasticache_clusters(self):
        extra = {
            'stackname': 'project-with-multiple-elasticaches--prod',
        }
        context = cfngen.build_context('project-with-multiple-elasticaches', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertIn('ElastiCache1', list(data['Resources'].keys()))
        self.assertIn('ElastiCache2', list(data['Resources'].keys()))
        # default parameter group
        self.assertEqual(
            {
                'CacheParameterGroupFamily': 'redis2.8',
                'Description': 'ElastiCache parameter group for project-with-multiple-elasticaches--prod',
                'Properties': {
                    'maxmemory-policy': 'volatile-lru',
                },
            },
            data['Resources']['ElastiCacheParameterGroup']['Properties']
        )
        self.assertEqual({'Ref': 'ElastiCacheParameterGroup'}, data['Resources']['ElastiCache1']['Properties']['CacheParameterGroupName'])
        # suppressed
        self.assertNotIn('ElastiCache3', list(data['Resources'].keys()))
        self.assertIn('ElastiCacheHost1', list(data['Outputs'].keys()))
        self.assertIn('ElastiCachePort1', list(data['Outputs'].keys()))
        self.assertIn('ElastiCacheHost2', list(data['Outputs'].keys()))
        self.assertIn('ElastiCachePort2', list(data['Outputs'].keys()))
        # suppressed
        self.assertNotIn('ElastiCacheHost3', list(data['Outputs'].keys()))
        self.assertNotIn('ElastiCachePort3', list(data['Outputs'].keys()))
        # overridden
        self.assertEqual('cache.t2.medium', data['Resources']['ElastiCache2']['Properties']['CacheNodeType'])
        self.assertEqual(
            {
                'CacheParameterGroupFamily': 'redis2.8',
                'Description': 'ElastiCache parameter group for project-with-multiple-elasticaches--prod cluster 2',
                'Properties': {
                    'maxmemory-policy': 'volatile-ttl',
                },
            },
            data['Resources']['ElastiCacheParameterGroup2']['Properties']
        )
        self.assertEqual({'Ref': 'ElastiCacheParameterGroup2'}, data['Resources']['ElastiCache2']['Properties']['CacheParameterGroupName'])

    def test_fully_overridden_elasticache_clusters_does_not_have_default_parameter_group(self):
        extra = {
            'stackname': 'project-with-fully-overridden-elasticaches--prod',
        }
        context = cfngen.build_context('project-with-fully-overridden-elasticaches', **extra)
        cfn_template = trop.render(context)
        data = self._parse_json(cfn_template)
        self.assertNotIn('ElastiCacheParameterGroup', list(data['Resources'].keys()))

    def test_overrides_scalar(self):
        context = {
            'elasticache': {
                'type': 'cache.t2.small',
                'engine': 'redis',
                'overrides': {
                    2: {
                        'type': 'cache.t2.medium',
                    }
                }
            }
        }
        self.assertEqual(
            {
                'engine': 'redis',
                'type': 'cache.t2.small',
            },
            trop.overridden_component(context, 'elasticache', 1, ['type'])
        )
        self.assertEqual(
            {
                'engine': 'redis',
                'type': 'cache.t2.medium',
            },
            trop.overridden_component(context, 'elasticache', 2, ['type'])
        )

    def test_overrides_dictionary(self):
        context = {
            'ec2': {
                'cluster-size': 2,
                'ext': {
                    'size': 30,
                    'device': '/dev/sdh',
                },
                'overrides': {
                    2: {
                        'ext': {
                            'size': 100,
                        }
                    }
                }
            }
        }
        self.assertEqual(
            {
                'cluster-size': 2,
                'ext': {
                    'device': '/dev/sdh',
                    'size': 30,
                }
            },
            trop.overridden_component(context, 'ec2', 1, ['ext'])
        )
        self.assertEqual(
            {
                'cluster-size': 2,
                'ext': {
                    'device': '/dev/sdh',
                    'size': 100,
                }
            },
            trop.overridden_component(context, 'ec2', 2, ['ext'])
        )

    def test_rds_deletion_policy_snapshot(self):
        "default rds deletion policy is 'Snapshot'"
        extra = {
            'stackname': 'dummy3--test',
            'alt-config': 'alt-config1'
        }
        context = cfngen.build_context('dummy3', **extra)
        data = self._parse_json(trop.render(context))
        self.assertEqual(context['rds']['deletion-policy'], "Snapshot")
        self.assertEqual(data['Resources']['AttachedDB']['DeletionPolicy'], 'Snapshot')

    def test_rds_deletion_policy_override(self):
        "an explicit deletion policy can be specified to override default"
        extra = {
            'stackname': 'dummy3--test',
            'alt-config': 'alt-config2'
        }
        context = cfngen.build_context('dummy3', **extra)
        data = self._parse_json(trop.render(context))
        self.assertEqual(context['rds']['deletion-policy'], "Delete")
        self.assertEqual(data['Resources']['AttachedDB']['DeletionPolicy'], 'Delete')

class TestIngress(base.BaseCase):
    def test_accepts_a_list_of_ports(self):
        simple_ingress = trop.Ingress.build([22, 80])
        self.assertEqual(
            self._dump_to_list_of_rules(simple_ingress),
            [
                {
                    'ToPort': 22,
                    'FromPort': 22,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 80,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ]
        )

    def test_accepts_remapped_ports(self):
        remapped_ingress = trop.Ingress.build(OrderedDict([
            (80, 8080),
        ]))
        self.assertEqual(
            self._dump_to_list_of_rules(remapped_ingress),
            [
                {
                    'ToPort': 8080,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ]
        )

    def test_accepts_ports_defining_custom_rules(self):
        custom_ingress = trop.Ingress.build(OrderedDict([
            (80, OrderedDict([
                ('guest', 8080),
                ('cidr-ip', '10.0.0.0/0'),
            ])),
            (10000, OrderedDict([
                ('guest', 10000),
                ('protocol', 'udp'),
                ('cidr-ip', '0.0.0.0/0'),
            ]))
        ]))
        self.assertEqual(
            self._dump_to_list_of_rules(custom_ingress),
            [
                {
                    'ToPort': 8080,
                    'FromPort': 80,
                    'CidrIp': '10.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 10000,
                    'FromPort': 10000,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'udp',
                },
            ]
        )

    def test_can_mix_and_match_definitions(self):
        custom_ingress = trop.Ingress.build([
            22,
            OrderedDict([(80, OrderedDict([
                ('guest', 8080),
            ]))]),
        ])
        self.assertEqual(
            self._dump_to_list_of_rules(custom_ingress),
            [
                {
                    'ToPort': 22,
                    'FromPort': 22,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 8080,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ]
        )

    def test_can_merge_multiple_sources(self):
        merged_ingress = trop.Ingress.build([22, 80]).merge(
            trop.Ingress.build([80, 443])
        )
        self.assertEqual(
            self._dump_to_list_of_rules(merged_ingress),
            [
                {
                    'ToPort': 22,
                    'FromPort': 22,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 80,
                    'FromPort': 80,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
                {
                    'ToPort': 443,
                    'FromPort': 443,
                    'CidrIp': '0.0.0.0/0',
                    'IpProtocol': 'tcp',
                },
            ]
        )

    def _dump_to_list_of_rules(self, ingress):
        return [r.to_dict() for r in ingress.to_troposphere()]
