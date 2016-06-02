from . import base
from time import sleep
from buildercore import cfngen, core, project

import logging
LOG = logging.getLogger(__name__)

class TestTrop(base.BaseCase):
    def setUp(self):
        self.test_region = 'us-east-1'

    def tearDown(self):
        pass

    def test_rendering(self):
        for pname in project.aws_projects().keys(): # !! needs fixtures
            LOG.info('rendering %s', pname)
            print cfngen.quick_render(pname)

    def test_validation(self):
        for pname in project.aws_projects().keys(): # !! needs fixtures
            template = cfngen.quick_render(pname)
            LOG.info('validating %s', pname)
            cfngen.validate_aws_template(pname, template)
            sleep(0.25) # helps avoid rate limiting.
