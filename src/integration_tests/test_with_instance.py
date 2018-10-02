import logging
from tests import base
from buildercore import bootstrap, cloudformation, utils, core
from buildercore.config import BOOTSTRAP_USER

logging.disable(logging.NOTSET) # re-enables logging during integration testing

LOG = logging.getLogger(__name__)

# the intent here is:
# * launch an ec2 instance without running highstate
# * run any logic against it that needs a running ec2 instance
# * optionally leave the instance running while debugging happens

class TestWithInstance(base.BaseIntegrationCase):
    @classmethod
    def setUpClass(cls):
        super(TestWithInstance, cls).setUpClass()
        cls.setup_stack(project='dummy1', explicitly_start=True)

    @classmethod
    def tearDownClass(cls):
        cls.tear_down_stack(cls)
        super(TestWithInstance, cls).tearDownClass()

    def test_bootstrap_create_stack_idempotence(self):
        "the same stack cannot be created multiple times"
        bootstrap.create_stack(self.stackname)

    def test_bootstrap_wait_until_in_progress(self):
        cloudformation._wait_until_in_progress(self.stackname)
        bootstrap.setup_ec2(self.stackname, self.context)

    def test_bootstrap_run_script(self):
        with core.stack_conn(self.stackname, username=BOOTSTRAP_USER):
            bootstrap.run_script('test.sh')

    def test_core_find_ec2_instances(self):
        self.assertEqual(len(core.find_ec2_instances(self.stackname)), 1) # 1 node is running
        self.assertEqual(len(core.find_ec2_instances(self.stackname, state='stopped', allow_empty=True)), 0) # 0 nodes are stopped

    def test_bootstrap_template_info(self):
        resp = bootstrap.template_info(self.stackname)
        expecting = {
            'stack_name': self.stackname,
            'stack_id': 'arn:aws:cloudformation:us-east-1:512686554592:stack/dummy1--luke-20180420025657-458624/afc10200-4459-11e8-8c52-500c2864aa35',
            'outputs': {
                'PublicIP1': '34.229.140.136',
                'AZ1': 'us-east-1d',
                'InstanceId1': 'i-027c0ae8fd9054cff',
                'PrivateIP1': '10.0.2.237'
            }
        }
        self.assertTrue(utils.hasallkeys(resp, expecting.keys()))
        self.assertTrue(utils.hasallkeys(resp['outputs'], expecting['outputs'].keys()))

    def test_bootstrap_write_environment_info(self):
        with core.stack_conn(self.stackname, username=BOOTSTRAP_USER):
            bootstrap.write_environment_info(self.stackname, overwrite=False)
            bootstrap.write_environment_info(self.stackname, overwrite=True)

    def test_core_describe_stack(self):
        core.describe_stack(self.stackname)

    def test_core_stack_is(self):
        self.assertTrue(core.stack_is_active(self.stackname))
        self.assertFalse(core.stack_is(self.stackname, ['fubar']))
        self.assertRaises(RuntimeError, core.stack_is, self.stackname, ['fubar'], core.ACTIVE_CFN_STATUS)

    def test_core_active_aws_stacks(self):
        active_stacks = core.active_aws_stacks(self.region, formatter=lambda stack: stack['StackName'])
        self.assertTrue(self.stackname in active_stacks)

    def test_core_steady_aws_stacks(self):
        "a 'steady' stack is a stack that isn't in transition from one state to another"
        steady_stacks = core.steady_aws_stacks(self.region, formatter=lambda stack: stack['StackName'])
        self.assertTrue(self.stackname in steady_stacks)

    def test_core_listfiles_remote(self):
        with core.stack_conn(self.stackname, username=BOOTSTRAP_USER):
            results = core.listfiles_remote('/')
            sublist = ['/tmp', '/bin', '/boot', '/var'] # /etc
            self.assertTrue(set(results) >= set(sublist))
