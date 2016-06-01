from . import base
from time import sleep
from buildercore import cfngen, core

import logging
LOG = logging.getLogger(__name__)

class TestTrop(base.BaseCase):
    def setUp(self):
        self.test_region = 'us-east-1'

    def tearDown(self):
        pass

    def test_rendering(self):
        cfngen.quick_render_all()

    def test_validation(self):
        conn = core.boto_cfn_conn(self.test_region)
        for pname, template in cfngen.quick_render_all():
            LOG.info('validating %s', pname)
            conn.validate_template(template)
            sleep(0.25) # helps avoid rate limiting.
