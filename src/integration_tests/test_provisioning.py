import os
from fabric.api import settings
from tests import base
from buildercore import bootstrap, cfngen, lifecycle
from buildercore.config import BOOTSTRAP_USER
import buildvars
import cfn

from fabfile import PROJECT_DIR

class TestProvisioning(base.BaseCase):
    def setUp(self):
        self.stacknames = []
        self.environment = self.generate_environment_name()

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

        tempfiles = [
            'ls',
            'venv/bin/less',
            'subfolder/pwd',
            'subfolder',
        ]
        for tf in tempfiles:
            path = os.path.join(PROJECT_DIR, tf)
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                # assumes dir is empty
                print 'should be empty:', os.listdir(path)
                os.rmdir(path)
            self.assertFalse(os.path.exists(path), "failed to delete path %r in tearDown" % path)

    def test_create(self):
        with settings(abort_on_prompts=True):
            project = 'dummy1'
            stackname = '%s--%s' % (project, self.environment)

            cfn.ensure_destroyed(stackname)
            self.stacknames.append(stackname)

            cfngen.generate_stack(project, stackname=stackname)
            bootstrap.create_stack(stackname)

            buildvars.switch_revision(stackname, 'master')
            buildvars.force(stackname, 'answer', 'forty-two')

            lifecycle.stop(stackname)
            lifecycle.start(stackname)

            cfn.cmd(stackname, "ls -l /", username=BOOTSTRAP_USER, concurrency='parallel')
            cfn.cmd(stackname, "ls -l /", username=BOOTSTRAP_USER, concurrency='parallel', node=1)

            cfn.download_file(stackname, "/bin/ls", "ls", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./ls"))

            cfn.download_file(stackname, "/bin/less", "venv/bin/", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./venv/bin/less"))

            cfn.download_file(stackname, "/bin/pwd", "subfolder/pwd", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./subfolder/pwd"))

class TestDeployment(base.BaseCase):
    def setUp(self):
        self.stacknames = []
        self.environment = self.generate_environment_name()

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

    def test_blue_green_operations(self):
        with settings(abort_on_prompts=True):
            project = 'project-with-cluster-integration-tests'
            stackname = '%s--%s' % (project, self.environment)

            cfn.ensure_destroyed(stackname)
            self.stacknames.append(stackname)
            cfngen.generate_stack(project, stackname=stackname)
            bootstrap.create_stack(stackname)

            import time
            time.sleep(30)

            output = cfn.cmd(stackname, 'ls -l /', username=BOOTSTRAP_USER, concurrency='blue-green')
            print output
