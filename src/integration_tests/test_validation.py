import pytest
from tests import base
from buildercore import cfngen, project
import logging
LOG = logging.getLogger(__name__)

logging.disable(logging.NOTSET) # re-enables logging during integration testing

# Depends on talking to AWS.

class TestValidationFixtures(base.BaseCase):
    def test_validation(self):
        "dummy projects and their alternative configurations pass validation"
        for pname in project.aws_projects().keys():
            cfngen.validate_project(pname)

class TestValidationElife():
    def setUp(self):
        # HERE BE DRAGONS
        # resets the testing config.SETTINGS_FILE we set in the base.BaseCase class
        base.switch_out_test_settings()

    def tearDown(self):
        base.switch_in_test_settings()

    @pytest.mark.parametrize("pname", project.aws_projects().keys())
    def test_validation_elife_projects(self, pname):
        "elife projects (and their alternative configurations) that come with the builder pass validation"

        cfngen.validate_project(pname)
