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
