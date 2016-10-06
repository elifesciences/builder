from . import base
from cfn import ssh, owner_ssh
from mock import patch

class TestBuildercoreBootstrap(base.BaseCase):
    @patch('cfn.local')
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.core.stack_data')
    def test_ssh_task(self, stack_data, active_stack_names, local):
        self._dummy_instance_is_active(stack_data, active_stack_names)
        ssh('dummy1--prod')
        local.assert_called_with('ssh elife@54.54.54.54')

    @patch('cfn.local')
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.core.stack_data')
    def test_owner_ssh_task(self, stack_data, active_stack_names, local):
        self._dummy_instance_is_active(stack_data, active_stack_names)
        owner_ssh('dummy1--prod')
        (args, _) = local.call_args
        self.assertRegexpMatches(args[0], 'ssh ubuntu@54.54.54.54 -i .+/.cfn/keypairs/dummy1--prod.pem')

    def _dummy_instance_is_active(self, stack_data, active_stack_names):
        active_stack_names.return_value = ['dummy1--prod']
        stack_data.return_value = [
            {
                'instance': {
                    'ip_address': '54.54.54.54'
                }
            }
        ]
