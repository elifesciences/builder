from . import base
from buildercore import bootstrap
from mock import patch, MagicMock

class TestBuildercoreBootstrap(base.BaseCase):
    @patch('buildercore.core.boto_sqs_conn')
    @patch('buildercore.core.boto_sns_conn')
    def test_setup_sqs(self, boto_sns_conn, boto_sqs_conn):
        sns = MagicMock()
        boto_sns_conn.return_value = sns

        bootstrap.setup_sqs('project-with-sqs--ci', {'search': ['articles', 'podcasts']}, 'us-east-1')

        sns.subscribe_sqs_queue.assert_called()
