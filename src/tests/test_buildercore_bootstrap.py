from . import base
from buildercore import bootstrap, cfngen
import cfn
from mock import patch, call, MagicMock

class TestBuildercoreBootstrap(base.BaseCase):
    def __init__(self, *args, **kwargs):
        super(TestBuildercoreBootstrap, self).__init__(*args, **kwargs)
        self.stacknames = []

    @patch('buildercore.core.boto_sqs_conn')
    @patch('buildercore.core.boto_sns_conn')
    def test_setup_sqs(self, boto_sns_conn, boto_sqs_conn):
        sns = MagicMock()
        boto_sns_conn.return_value = sns

        bootstrap.setup_sqs('project-with-sqs--ci', {'search': ['articles', 'podcasts']}, 'us-east-1')

        sns.subscribe_sqs_queue.assert_called()

    def test_create(self):
        stackname = 'dummy1--test'
        self.stacknames.append(stackname)

        cfngen.generate_stack('dummy1', stackname=stackname)
        bootstrap.create_stack(stackname)

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

