from . import base
from buildercore import bootstrap
from buildercore.utils import yaml_dumps
import mock, json
from os.path import join

class TestBuildercoreBootstrap(base.BaseCase):
    def test_master_configuration(self):
        formulas = ['https://github.com/elifesciences/journal-formula', 'https://github.com/elifesciences/lax-formula']
        master_configuration_template = open('src/tests/fixtures/etc-salt-master.template', 'r')
        master_configuration = bootstrap.expand_master_configuration(master_configuration_template, formulas)
        master_configuration_yaml = yaml_dumps(master_configuration)
        expected_configuration = """auto_accept: true
interface: 0.0.0.0
log_level: info
fileserver_backend:
- roots
file_roots:
    base:
    - /opt/builder-private/salt/
    - /opt/formulas/journal/salt/
    - /opt/formulas/lax/salt/
    - /opt/formulas/builder-base/
pillar_roots:
    base:
    - /opt/builder-private/pillar
"""
        self.assertEqual(master_configuration_yaml, expected_configuration)

    def test_unsub_sqs(self):
        stackname = 'observer--end2end'
        fixture = json.load(open(join(self.fixtures_dir, 'sns_subscriptions.json'), 'r'))
        with mock.patch('buildercore.core._all_sns_subscriptions', return_value=fixture):
            # observer no longer wants to subscribe to metrics
            context = {stackname: ['bus-articles--end2end', 'bus-metrics--end2end']}
            del context[stackname][1]

            actual = bootstrap.unsub_sqs(stackname, context, 'someregion', dry_run=True)
            expected = (
                {
                    stackname: [{'Endpoint': 'arn:aws:sqs:us-east-1:512686554592:observer--end2end',
                                 'Owner': '512686554592',
                                 'Protocol': 'sqs',
                                 'SubscriptionArn': 'arn:aws:sns:us-east-1:512686554592:bus-metrics--end2end:71f61023-3905-40bb-9f7c-0ce710175212',
                                 'Topic': 'bus-metrics--end2end',
                                 'TopicArn': 'arn:aws:sns:us-east-1:512686554592:bus-metrics--end2end'}]
                },
                {
                    'observer--end2end': ['arn:aws:sns:us-east-1:512686554592:bus-metrics--end2end'],
                },
            )
            self.assertEqual(expected, actual)

    def test_remove_topics_from_sqs_policy(self):
        original = {
            'Version': '2008-10-17',
            'Statement': [
                {
                    # ...
                    'Condition': {
                        'StringLike': {
                            'aws:SourceArn': 'arn:aws:sns:us-east-1:512686554592:bus-articles--end2end',
                        },
                    },
                },
                {
                    # ...
                    'Condition': {
                        'StringLike': {
                            'aws:SourceArn': 'arn:aws:sns:us-east-1:512686554592:bus-press-packages--end2end',
                        },
                    },
                },
            ],
        }

	cleaned = bootstrap.remove_topics_from_sqs_policy(original, ['arn:aws:sns:us-east-1:512686554592:bus-articles--end2end'])
	self.assertEqual(
            cleaned,
            {
                'Version': '2008-10-17',
                'Statement': [
                    {
                        # ...
                        'Condition': {
                            'StringLike': {
                                'aws:SourceArn': 'arn:aws:sns:us-east-1:512686554592:bus-press-packages--end2end',
                            },
                        },
                    },
                ],
            }
	)
