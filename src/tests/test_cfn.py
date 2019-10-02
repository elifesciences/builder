import os
from . import base
from buildercore import cfngen, context_handler
from cfn import ssh, owner_ssh, generate_stack_from_input
from mock import patch, MagicMock

class TestCfn(base.BaseCase):
    def setUp(self):
        os.environ['LOGNAME'] = 'my_user'

    def tearDown(self):
        del os.environ['LOGNAME']

    @patch('cfn.local')
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.context_handler.load_context')
    @patch('buildercore.core.find_ec2_instances')
    def test_ssh_task(self, find_ec2_instances, load_context, active_stack_names, local):
        self._dummy_instance_is_active(find_ec2_instances, load_context, active_stack_names)
        ssh('dummy1--prod')
        local.assert_called_with('ssh elife@54.54.54.54 -i ~/.ssh/id_rsa')

    @patch('cfn.local')
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.context_handler.load_context')
    @patch('buildercore.core.find_ec2_instances')
    def test_owner_ssh_task(self, find_ec2_instances, load_context, active_stack_names, local):
        self._dummy_instance_is_active(find_ec2_instances, load_context, active_stack_names)
        owner_ssh('dummy1--prod')
        (args, _) = local.call_args
        self.assertRegex(args[0], 'ssh ubuntu@54.54.54.54 -i .+/.cfn/keypairs/dummy1--prod.pem')

    # all non-interactive cases
    def test_generate_stack_from_input(self):
        prod = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy1', prod, 'prod'), 'dummy1--%s' % prod)
        alt_config = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy2', alt_config, 'alt-config1'), 'dummy2--%s' % alt_config)
        end2end = base.generate_environment_name()
        self.assertEqual(generate_stack_from_input('dummy2', end2end, alt_config='alt-config1'), 'dummy2--%s' % end2end)

    @patch('cfn.local')
    @patch('buildercore.core.active_stack_names')
    @patch('buildercore.core.find_ec2_instances')
    def test_altconfig_name_preserved(self, *args):
        #import pprint

        # create a random instance id for the 'dummy2' project and use the 'alt-config1' alt-config
        # see: fixtures/dummy2-project.json
        instance_id = base.generate_environment_name() # "luke-20191001045227-270172"
        stackname = generate_stack_from_input('dummy2', instance_id, alt_config='alt-config1') # "dummy2--luke-20191001045222-883274"

        # ensure alt-config is in there and correct
        current_context = context_handler.load_context(stackname)

        #print('current context')
        # pprint.pprint(current_context)

        # skip calling update_infrastructure, we just want to test the diff with any changes
        more_context = {
            # todo: not working
            #'rds': {
            #    'allow-major-version-upgrade': True
            #}
        }
        new_context, delta, _ = cfngen.regenerate_stack(stackname, **more_context)

        # ensure the alt-config value is correct (it was previously the instance-id)
        self.assertEqual(current_context['alt-config'], new_context['alt-config'])

        # TODO: ensure the change in more_context is found in the new context and is present in the delta

        #print('new context')
        # pprint.pprint(new_context)

        # print('---')

        # print('delta')
        # pprint.pprint(delta)

        # self.assertTrue(False)

    def _dummy_instance_is_active(self, find_ec2_instances, load_context, active_stack_names):
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
