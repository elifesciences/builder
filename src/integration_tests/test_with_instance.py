import os, json
from fabric.api import settings
from tests import base
from buildercore import bootstrap, cfngen, cloudformation, lifecycle, utils, core, config
from buildercore.config import BOOTSTRAP_USER
import cfn
import logging
#import mock

logging.disable(logging.NOTSET) # re-enables logging during integration testing

LOG = logging.getLogger(__name__)

# the intent here is:
# * launch an ec2 instance without running highstate
# * run any logic against it that needs a running ec2 instance
# * optionally leave the instance running while debugging happens

class One(base.BaseCase):
    @classmethod
    def setUpClass(self): # cls, not self
        super(One, self).setUpClass()
        base.switch_in_test_settings()

        # to re-use an existing stack, ensure self.reuse_existing_stack is True
        # this will read the instance name from a temporary file (if it exists) and
        # look for that, creating it if doesn't exist yet
        # also ensure self.cleanup is False so the instance isn't destroyed after tests complete
        self.reuse_existing_stack = config.TWI_REUSE_STACK
        self.cleanup = config.TWI_CLEANUP

        self.stacknames = []
        self.environment = base.generate_environment_name()
        # self.temp_dir, self.rm_temp_dir = utils.tempdir()

        # debugging only, where we keep an instance up between processes
        self.state, self.statefile = {}, '/tmp/.open-test-instances.txt'
        project = 'dummy1'

        if self.reuse_existing_stack and os.path.exists(self.statefile):
            # evidence of a previous instance and we've been told to re-use old instances
            old_state = json.load(open(self.statefile, 'r'))
            old_env = old_state.get('environment')

            # test if the old stack still exists ...
            if old_env and core.describe_stack(project + "--" + old_env, allow_missing=True):
                self.state = old_state
                self.environment = old_env
            else:
                # nope. old statefile is bogus, delete it
                os.unlink(self.statefile)

        self.state['environment'] = self.environment # will be saved later

        with settings(abort_on_prompts=True):
            self.stackname = '%s--%s' % (project, self.environment)
            self.stacknames.append(self.stackname)

            if self.cleanup:
                cfn.ensure_destroyed(self.stackname)

            self.context, self.cfn_template, _ = cfngen.generate_stack(project, stackname=self.stackname)
            self.region = self.context['project']['aws']['region']
            bootstrap.create_stack(self.stackname)

            lifecycle.start(self.stackname)

    @classmethod
    def tearDownClass(self): # cls, not self
        super(One, self).tearDownClass()
        try:
            if self.reuse_existing_stack:
                json.dump(self.state, open(self.statefile, 'w'))
            if self.cleanup:
                for stackname in self.stacknames:
                    cfn.ensure_destroyed(stackname)
            # self.rm_temp_dir()
            # self.assertFalse(os.path.exists(self.temp_dir), "failed to delete path %r in tearDown" % self.temp_dir)
        except BaseException:
            # important, as anything in body will silently fail
            LOG.exception('uncaught error tearing down test class')

    def test_bootstrap_create_stack_idempotence(self):
        "the same stack cannot be created multiple times"
        bootstrap.create_stack(self.stackname)

    def test_bootstrap_wait_until_in_progress(self):
        cloudformation._wait_until_in_progress(self.stackname)
        bootstrap.setup_ec2(self.stackname, self.context)

    # TODO: transform this into a cloudformation module test
    #def test_bootstrap_update_template_no_updates(self):
    #    "a template with no changes can be updated with no problems"
    #    bootstrap.update_template(self.stackname, json.load(open(self.cfn_template, 'r')))

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
