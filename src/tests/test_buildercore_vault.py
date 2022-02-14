import json
from unittest.mock import patch
from buildercore import vault
from . import base

class TokenCreation(base.BaseCase):
    @patch('buildercore.external.execute')
    def test_token_create_for_masterless(self, exec_stub):
        exec_stub.return_value = json.dumps({
            # ...
            'auth': {
                'client_token': '1806b7a1-45a4-441d-888f-414ac9d5680f',
            },
        })
        token = vault.token_create(
            vault_addr='https://some-vault.org',
            policy='somewhat-powerful',
            display_name='dummy1--some-test'
        )
        self.assertEqual(token, '1806b7a1-45a4-441d-888f-414ac9d5680f')
