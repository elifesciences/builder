from buildercore import cloudformation
from . import base
import botocore

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

