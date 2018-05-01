import os, json
from fabric.api import settings
from tests import base
from buildercore import bootstrap, cfngen, lifecycle, core, config

import cfn
import logging


logging.disable(logging.NOTSET) # re-enables logging during integration testing

LOG = logging.getLogger(__name__)

# the intent here is:
# * launch multiple ec2 instances without running highstate
# * run any logic that requires multiple ec2 nodes
# * optionally leave the nodes running while debugging happens

# TODO: this class is a copy with `test_with_instance.py` with one value tweaked
# turn into a base class perhaps?
class One(base.BaseCase):
    @classmethod
    def setUpClass(self): # cls, not self
        super(One, self).setUpClass()

        # to re-use an existing stack, ensure self.reuse_existing_stack is True
        # this will read the instance name from a temporary file (if it exists) and
        # look for that, creating it if doesn't exist yet
        # also ensure self.cleanup is False so the stack isn't destroyed after tests complete
        self.reuse_existing_stack = config.TWI_REUSE_STACK
        self.cleanup = config.TWI_CLEANUP

        self.stacknames = []
        self.environment = base.generate_environment_name()
        # self.temp_dir, self.rm_temp_dir = utils.tempdir()

        # debugging only, where we keep an instance up between processes
        self.state, self.statefile = {}, '/tmp/.open-test-instances.txt'
        project = 'project-with-cluster-integration-tests'

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

            # lifecycle.start(self.stackname) # see self.setUp

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

    def setUp(self):
        lifecycle.start(self.stackname)

    def test_restart_all_started(self):
        "multiple nodes can be restarted from a running state"
        lifecycle.restart(self.stackname)

    def test_restart_all_stopped(self):
        "multiple nodes can be restarted from a stopped state"
        lifecycle.stop(self.stackname)
        lifecycle.restart(self.stackname)

    def test_restart_one_stopped(self):
        "multiple nodes can be restarted from a mixed state"
        node1 = core.find_ec2_instances(self.stackname)[0]
        node1.stop()
        node1.wait_until_stopped()
        lifecycle.restart(self.stackname)
