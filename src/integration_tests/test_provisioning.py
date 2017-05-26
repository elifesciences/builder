import os
from datetime import datetime
from subprocess import check_output
from fabric.api import settings
from tests import base
from buildercore import bootstrap, cfngen, lifecycle
from buildercore.config import BOOTSTRAP_USER
import buildvars
import cfn

def generate_environment_name():
    """to avoid multiple people clashing while running their builds
       and new builds clashing with older ones"""
    return check_output('whoami').rstrip() + datetime.utcnow().strftime("%Y%m%d%H%M%S")

class TestProvisioning(base.BaseCase):
    def setUp(self):
        self.stacknames = []
        self.environment = generate_environment_name()

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

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
            cfn.download_file(stackname, "/bin/ls", "ls", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./ls"))
            cfn.download_file(stackname, "/bin/less", "venv/bin/", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./venv/bin/less"))

            cfn.download_file(stackname, "/bin/pwd", "subfolder/pwd", use_bootstrap_user="true")
            self.assertTrue(os.path.isfile("./subfolder/pwd"))

class TestDeployment(base.BaseCase):
    def setUp(self):
        self.stacknames = []
        self.environment = generate_environment_name()

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

            output = cfn.cmd(stackname, 'ls -l /', username=BOOTSTRAP_USER, concurrency='blue-green')
            print output
