from subprocess import check_output
from fabric.api import settings
from tests import base
from buildercore import bootstrap, cfngen
import buildvars
import cfn

class TestProvisioning(base.BaseCase):
    def setUp(self):
        self.stacknames = []
        # to avoid multiple people clashing while running their buils
        self.environment = check_output('whoami').rstrip()

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

    def test_create(self):
        with settings(abort_on_prompts=True):
            project = 'dummy1'
            stackname = '%s--%s' % (project, self.environment)

            cfn.ensure_destroyed(stackname)
            self.stacknames.append(stackname) # ensures stack is destroyed

            cfngen.generate_stack(project, stackname=stackname)
            bootstrap.create_stack(stackname)

            # TODO: hangs, not ready to test this. Will revisit in the future
            #buildvars.switch_revision(stackname, 'master')
