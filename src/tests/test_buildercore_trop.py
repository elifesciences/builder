from pprint import pprint
from os.path import join
import json
from . import base
from buildercore import cfngen, trop, config, utils

class TestBuildercoreTrop(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

    def tearDown(self):
        pass

    def test_dns_template_contains_external_and_internal_dns(self):
        extra = {
            'stackname': 'dummy2--test',
        }
        context = cfngen.build_context('dummy2', **extra)

        self.assertEqual(context['project_hostname'], "dummy2.example.org")
        self.assertEqual(context['full_hostname'], "test--dummy2.example.org")
        self.assertEqual(context['int_full_hostname'], "test--dummy2.example.internal")
        cfn_template = trop.render(context)
        data = json.loads(trop.render(context))

        self.assertIn('ExtDNS', data['Resources'])
        ext_dns = data['Resources']['ExtDNS']['Properties']
        self.assertEqual(ext_dns['Name'], 'test--dummy2.example.org')
        self.assertEqual(ext_dns['HostedZoneName'], 'example.org.')
        self.assertEqual(ext_dns['Type'], 'A')

        self.assertIn('IntDNS', data['Resources'])
        int_dns = data['Resources']['IntDNS']['Properties']
        self.assertEqual(int_dns['Name'], 'test--dummy2.example.internal')
        self.assertEqual(int_dns['HostedZoneName'], 'example.internal.')
        self.assertEqual(int_dns['Type'], 'A')

    def test_production_dns_template_has_a_canonical_and_a_consistent_hostname(self):
        extra = {
            'stackname': 'dummy2--prod',
        }
        context = cfngen.build_context('dummy2', **extra)

        self.assertEqual(context['project_hostname'], "dummy2.example.org")
        self.assertEqual(context['full_hostname'], "prod--dummy2.example.org")

        cfn_template = trop.render(context)
        data = json.loads(trop.render(context))

        self.assertIn('ExtDNS', data['Resources'])
        ext_dns = data['Resources']['ExtDNS']['Properties']
        self.assertEqual(ext_dns['Name'], 'prod--dummy2.example.org')

        self.assertIn('ExtDNSProd', data['Resources'])
        ext_dns = data['Resources']['ExtDNSProd']['Properties']
        self.assertEqual(ext_dns['Name'], 'dummy2.example.org')

        self.assertEqual(data['Outputs']['DomainName']['Value'], {'Ref': 'ExtDNSProd'})

    def test_rds_template_contains_rds(self):
        extra = {
            'stackname': 'dummy3--test',
            'alt-config': 'alt-config1'
        }
        context = cfngen.build_context('dummy3', **extra)
        self.assertEqual(context['rds_dbname'], "dummy3test")
        self.assertEqual(context['rds_instance_id'], "dummy3-test")
        self.assertTrue(context['project']['aws'].has_key('rds'))
        cfn_template = trop.render(context)
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
                'AvailabilityZone': {'Fn::GetAtt': ['EC2Instance', 'AvailabilityZone']},
                'VolumeType': 'standard',
                'Size': '200',
            },
            data['Resources']['ExtraStorage']['Properties']
        )
