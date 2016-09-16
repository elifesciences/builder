from os.path import join
import json
from . import base
from buildercore import cfngen, trop, utils

class TestBuildercoreTrop(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

    def tearDown(self):
        pass

    def test_rds_template_contains_rds(self):
        extra = {
            'stackname': 'dummy3--test',
            'alt-config': 'alt-config1'
        }
        context = cfngen.build_context('dummy3', **extra)
        self.assertEqual(context['rds_dbname'], "dummy3test")
        self.assertEqual(context['rds_instance_id'], "dummy3-test")
        self.assertTrue(context['project']['aws'].has_key('rds'))
        data = json.loads(trop.render(context))
        self.assertTrue(isinstance(utils.lu(data, 'Resources.AttachedDB'), dict))

    def test_sns_template(self):
        extra = {
            'stackname': 'just-some-sns--prod',
        }
        context = cfngen.build_context('just-some-sns', **extra)
        cfn_template = trop.render(context)
        data = json.loads(cfn_template)
        self.assertEqual(['WidgetsProdTopic'], data['Resources'].keys())
        self.assertEqual(
            {'Type': 'AWS::SNS::Topic', 'Properties': {'TopicName': 'widgets-prod'}}, 
            data['Resources']['WidgetsProdTopic']
        )
        self.assertEqual(['WidgetsProdTopicArn'], data['Outputs'].keys())
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
        data = json.loads(cfn_template)
        self.assertEqual(['ProjectWithSqsIncomingProdQueue'], data['Resources'].keys())
        self.assertEqual(
            {'Type': 'AWS::SQS::Queue', 'Properties': {'QueueName': 'project-with-sqs-incoming-prod'}}, 
            data['Resources']['ProjectWithSqsIncomingProdQueue']
        )
        self.assertEqual(['ProjectWithSqsIncomingProdQueueArn'], data['Outputs'].keys())
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
        data = json.loads(cfn_template)
        self.assertIn('MountPoint', data['Resources'].keys())
        self.assertIn('ExtraStorage', data['Resources'].keys())
        self.assertEqual(
            {
                'AvailabilityZone': {'Fn::GetAtt': ['EC2Instance1', 'AvailabilityZone']},
                'VolumeType': 'standard',
                'Size': '200',
            },
            data['Resources']['ExtraStorage']['Properties']
        )

    def test_clustered_template(self):
        extra = {
            'stackname': 'project-with-cluster--prod',
        }
        context = cfngen.build_context('project-with-cluster', **extra)
        cfn_template = trop.render(context)
        data = json.loads(cfn_template)
        resources = data['Resources']
        self.assertIn('EC2Instance1', resources.keys())
        self.assertIn('EC2Instance2', resources.keys())
        self.assertIn('StackSecurityGroup', resources.keys())
        self.assertIn(
            {
                'Key': 'Name',
                'Value': 'project-with-cluster--prod--1',
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
        self.assertIn('InstanceId1', outputs.keys())
        self.assertEqual({'Ref': 'EC2Instance1'}, outputs['InstanceId1']['Value'])
        self.assertEqual({'Ref': 'EC2Instance1'}, outputs['InstanceId1']['Value'])
        self.assertIn('ElasticLoadBalancer', resources.keys())
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
                'LoadBalancerPort': '80',
                'Protocol': 'HTTP',
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
        self.assertNotIn('IntDNS', resources.keys())
        dns = resources['ExtDNS']['Properties']
        self.assertIn('AliasTarget', dns.keys())
        self.assertEqual(dns['Name'], 'prod--project-with-cluster.example.org')
        self.assertIn('DomainName', outputs.keys())

