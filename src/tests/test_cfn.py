import pytest
import re
import os
import utils
from . import base
from buildercore import cfngen, context_handler
from cfn import ssh, owner_ssh, generate_stack_from_input
from mock import patch, MagicMock

# warn: this module uses fixtures implicitly loaded from `./src/conftest.py`

def _dummy_instance_is_active(find_ec2_instances, load_context, active_stack_names):
    """populates mock objects with dummy values.
    simulates a 'prod' instance of the 'dummy1' project."""
    active_stack_names.return_value = ['dummy1--prod']
    load_context.return_value = {
        'ec2': {
            'cluster-size': 1,
        },
    }
    instance = MagicMock()
    instance.public_ip_address = '54.54.54.54'
    instance.tags = [{'Key': 'Name', 'Value': 'dummy1--test--1'}]
    find_ec2_instances.return_value = [
        instance
    ]

@patch('cfn.local')
@patch('buildercore.core.active_stack_names')
@patch('buildercore.context_handler.load_context')
@patch('buildercore.core.find_ec2_instances')
def test_ssh_task(find_ec2_instances, load_context, active_stack_names, local, test_projects):
    _dummy_instance_is_active(find_ec2_instances, load_context, active_stack_names)
    ssh('dummy1--prod')
    local.assert_called_with('ssh -o "ConnectionAttempts 3" elife@54.54.54.54 -i ~/.ssh/id_rsa')

@patch('cfn.local')
@patch('buildercore.core.active_stack_names')
@patch('buildercore.context_handler.load_context')
@patch('buildercore.core.find_ec2_instances')
def test_owner_ssh_task(find_ec2_instances, load_context, active_stack_names, local, test_projects):
    _dummy_instance_is_active(find_ec2_instances, load_context, active_stack_names)
    owner_ssh('dummy1--prod')
    (args, _) = local.call_args
    regex = 'ssh -o "ConnectionAttempts 3" ubuntu@54.54.54.54 -i .+/.cfn/keypairs/dummy1--prod.pem'
    assert re.search(regex, args[0])

def test_launch_project_with_unique_altconfig(test_projects):
    "calling the `launch` task with a unique alt-config should fail"
    pname = 'project-with-unique-alt-config'
    instance_id = base.generate_environment_name()
    alt_config = 'prod'
    with patch('buildercore.core.stack_is_active', return_value=True):
        with pytest.raises(utils.TaskExit) as exc:
            expected_msg = "stack 'project-with-unique-alt-config--prod' exists, cannot re-use unique configuration 'prod'."
            generate_stack_from_input(pname, instance_id, alt_config)
        assert str(exc.value) == expected_msg

class TestCfn(base.BaseCase):
    def setUp(self):
        os.environ['LOGNAME'] = 'my_user'

    def tearDown(self):
        del os.environ['LOGNAME']

    # all non-interactive cases
    @patch('buildercore.core.describe_stack')
    @patch('buildercore.context_handler.load_context', context_handler._load_context_from_disk)
    def test_generate_stack_from_input(self, *args):
        prod = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy1', prod, 'prod'), 'dummy1--%s' % prod)
        alt_config = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy2', alt_config, alt_config='alt-config1'), 'dummy2--%s' % alt_config)
        end2end = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy2', end2end, alt_config='alt-config1'), 'dummy2--%s' % end2end)

    # lsh@2021-06-22, todo: very long test (4s), fix.
    @patch('buildercore.core.describe_stack')
    @patch('buildercore.context_handler.load_context', context_handler._load_context_from_disk)
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.core.find_ec2_instances')
    def test_altconfig_name_preserved(self, *args):
        # create a random instance id for the 'dummy2' project and use the 'alt-config1' alt-config
        # see: fixtures/dummy2-project.json
        instance_id = base.generate_environment_name() # "luke-20191001045227-270172"
        stackname = generate_stack_from_input('dummy2', instance_id, alt_config='alt-config1') # "dummy2--luke-20191001045222-883274"

        # ensure alt-config is in there and correct
        current_context = context_handler.load_context(stackname)
        self.assertEqual('alt-config1', current_context['alt-config'])

        # skip calling update_infrastructure, we just want to test the diff with any changes
        new_context = cfngen.regenerate_stack(stackname)[0]

        # ensure the alt-config value is correct (it was previously the instance-id)
        self.assertEqual(current_context['alt-config'], new_context['alt-config'])
