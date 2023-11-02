import json
from unittest.mock import MagicMock, patch

import botocore
from buildercore import cloudformation

from . import base


def test_troposphere_v2_template_upgraded_to_v3_template():
    "`cloudformation.read_template` will upgrade any Troposphere v2 string-booleans to v3 literal booleans."
    v3_fixture = json.loads(base.fixture("cloudformation/project-with-troposphere-v3-template.json"))
    v2_fixture_path = base.fixture_path("cloudformation/project-with-troposphere-v2-template.json")
    assert v3_fixture == cloudformation._read_template(v2_fixture_path)

class StackCreationContextManager(base.BaseCase):
    def test_catches_already_existing_stack_and_continues(self):
        with cloudformation.stack_creation('dummy1--test'):
            raise botocore.exceptions.ClientError(
                {
                    'ResponseMetadata': {'RetryAttempts': 0, 'HTTPStatusCode': 400, 'RequestId': '55408f12-64e6-11e8-b06f-8bac24811007', 'HTTPHeaders': {'x-amzn-requestid': '55408f12-64e6-11e8-b06f-8bac24811007', 'date': 'Thu, 31 May 2018 15:21:47 GMT', 'content-length': '297', 'content-type': 'text/xml', 'connection': 'close'}},
                    'Error': {
                        'Message': 'Stack [dummy1--test] already exists',
                        'Code': 'AlreadyExistsException',
                        'Type': 'Sender'
                    }
                },
                'CreateStack'
            )

class StackInformation(base.BaseCase):
    @patch('buildercore.cloudformation.core.describe_stack')
    def test_read_output(self, describe_stack):
        description = MagicMock()
        description.meta.data = {
            'Outputs': [
                {
                    'OutputKey': 'ElasticLoadBalancer',
                    'OutputValue': 'dummy1--t-ElasticL-19CB72BN8E36S',
                    # ...
                }
            ],
        }
        describe_stack.return_value = description

        self.assertEqual(
            cloudformation.read_output('dummy1--test', 'ElasticLoadBalancer'),
            'dummy1--t-ElasticL-19CB72BN8E36S'
        )

class StackUpdate(base.BaseCase):
    def test_no_updates(self):
        cloudformation.update_template('dummy1--test', cloudformation.CloudFormationDelta())

class ApplyDelta(base.BaseCase):
    def test_apply_delta_may_add_edit_and_remove_resources(self):
        template = {
            'Resources': {
                'A': 1,
                'B': 2,
                'C': 3,
            }
        }
        cloudformation.apply_delta(template, cloudformation.CloudFormationDelta({'Resources': {'D': 4}}, {'Resources': {'C': 30}}, {'Resources': {'B': 2}}))
        self.assertEqual(template, {'Resources': {'A': 1, 'C': 30, 'D': 4}})

    def test_apply_delta_may_add_components_which_werent_there(self):
        template = {
            'Resources': {
                'A': 1,
            }
        }
        cloudformation.apply_delta(template, cloudformation.CloudFormationDelta({'Outputs': {'B': 2}}, {}, {}))
        self.assertEqual(template, {'Resources': {'A': 1}, 'Outputs': {'B': 2}})
