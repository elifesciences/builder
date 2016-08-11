import os, boto
from . import base
from time import sleep
from buildercore import cfngen, project, config

import logging
LOG = logging.getLogger(__name__)

class TestBuildercoreCfngen(base.BaseCase):
    def setUp(self):
        self.test_region = 'us-east-1'

    def tearDown(self):
        pass

    def test_rendering(self):
        for pname in project.aws_projects().keys():
            LOG.info('rendering %s', pname)
            cfngen.quick_render(pname)

    def test_validation(self):
        "dummy projects and their alternative configurations pass validation"
        for pname in project.aws_projects().keys():
            self.assertTrue(cfngen.validate_project(pname))
            sleep(0.25)

    def test_validation_elife_projects(self):
        "elife projects (and their alternative configurations) that come with the builder pass validation"

        # HERE BE DRAGONS
        # resets the testing config.SETTINGS_FILE we set in the base.BaseCase class
        self.switch_out_test_settings()
        
        for pname in project.aws_projects().keys():
            self.assertTrue(cfngen.validate_project(pname))
            sleep(0.25)

        self.switch_in_test_settings()
