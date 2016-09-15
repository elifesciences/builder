from tests import base
from buildercore import bootstrap, cfngen
import cfn

class TestProvisioning(base.BaseCase):
    def setUp(self):
        self.stacknames = []

    def tearDown(self):
        for stackname in self.stacknames:
            cfn.ensure_destroyed(stackname)

    def test_create(self):
        stackname = 'dummy1--test'
        self.stacknames.append(stackname) # ensures stack is destroyed

        cfngen.generate_stack('dummy1', stackname=stackname)
        bootstrap.create_stack(stackname)
