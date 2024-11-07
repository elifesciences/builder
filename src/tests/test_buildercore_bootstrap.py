import json
from os.path import join
from unittest import mock

from buildercore import bootstrap
from buildercore.utils import yaml_dumps

from . import base


class TestBuildercoreBootstrap(base.BaseCase):
    def test_master_configuration(self):
        formulas = ['https://github.com/elifesciences/journal-formula', 'https://github.com/elifesciences/lax-formula']
        with open('src/tests/fixtures/etc-salt-master.template') as fh:
            master_configuration = bootstrap.expand_master_configuration(fh.read(), formulas)
        master_configuration_yaml = yaml_dumps(master_configuration)
        expected_configuration = """auto_accept: true
interface: 0.0.0.0
log_level: info
fileserver_backend:
- roots
file_roots:
    base:
    - /opt/builder-private/salt/
    - /opt/builder-configuration/salt/
    - /opt/formulas/journal/salt/
    - /opt/formulas/lax/salt/
    - /opt/formulas/builder-base/
pillar_roots:
    base:
    - /opt/builder-private/pillar
    - /opt/builder-configuration/pillar
"""
        self.assertEqual(master_configuration_yaml, expected_configuration)

    def test_unsub_sqs(self):
        stackname = 'observer--end2end'
        with open(join(self.fixtures_dir, 'sns_subscriptions.json')) as fh:
            subs_fixture = json.load(fh)
        with mock.patch('buildercore.core._all_sns_subscriptions', return_value=subs_fixture):
            old_context = {'sqs':{stackname: ['bus-articles--end2end', 'bus-metrics--end2end']}}
            with mock.patch('buildercore.context_handler.load_context', return_value=old_context):
                # observer no longer wants to subscribe to metrics
                new_context = dict(old_context)
                del new_context['sqs'][stackname][1]

                actual = bootstrap.unsub_sqs(stackname, new_context['sqs'], 'someregion', dry_run=True)
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
                        stackname: ['arn:aws:sns:us-east-1:512686554592:bus-metrics--end2end'],
                    },
                )
                self.assertEqual(expected, actual)

    def test_unsub_sqs_detect_multiple_subs(self):
        "when multiple subscriptions to a single topic exist, unsusbscribe from them"
        stackname = 'observer--end2end'
        with open(join(self.fixtures_dir, 'sns_subscriptions.json')) as fh:
            fixture = json.load(fh)

        multiple_sub_same_topic = {
            "Topic": "bus-articles--end2end",
            "Endpoint": "arn:aws:sqs:us-east-1:512686554592:observer--end2end",
            "Protocol": "sqs",
            "Owner": "512686554592",
            "TopicArn": "arn:aws:sns:us-east-1:512686554592:bus-articles--end2end",
            "SubscriptionArn": "arn:aws:sns:us-east-1:512686554592:bus-articles--end2end:foobar"
        }
        # order is important, most recent sub loses out
        #fixture.insert(0, multiple_sub_same_topic)
        fixture.append(multiple_sub_same_topic)

        with mock.patch('buildercore.core._all_sns_subscriptions', return_value=fixture):
            context = {'sqs': {stackname: ['bus-articles--end2end', 'bus-metrics--end2end']}}
            with mock.patch('buildercore.context_handler.load_context', return_value=context):
                actual = bootstrap.unsub_sqs(stackname, context['sqs'], 'someregion', dry_run=True)
                expected_unsub_map = {
                    stackname: [
                        {'Endpoint': 'arn:aws:sqs:us-east-1:512686554592:observer--end2end',
                        'Owner': '512686554592',
                        'Protocol': 'sqs',
                        'SubscriptionArn': 'arn:aws:sns:us-east-1:512686554592:bus-articles--end2end:foobar',
                        'Topic': 'bus-articles--end2end',
                        'TopicArn': 'arn:aws:sns:us-east-1:512686554592:bus-articles--end2end'}]}
                expected_perm_map = {
                    'observer--end2end': ['arn:aws:sns:us-east-1:512686554592:bus-articles--end2end']}
                expected = (expected_unsub_map, expected_perm_map)
                assert expected == actual

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

    def test_remove_all_topics_from_sqs_policy(self):
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
            ],
        }

        cleaned = bootstrap.remove_topics_from_sqs_policy(original, ['arn:aws:sns:us-east-1:512686554592:bus-articles--end2end'])
        self.assertIsNone(cleaned)
