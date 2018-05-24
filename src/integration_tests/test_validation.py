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
    @classmethod
    def setup_class(cls):
        # HERE BE DRAGONS
        # resets the testing config.SETTINGS_FILE we set in the base.BaseCase class
        base.switch_out_test_settings()

    @classmethod
    def teardown_class(cls):
        base.switch_in_test_settings()

    @pytest.mark.parametrize("project_name", project.aws_projects().keys())
    def test_validation_elife_projects(self, project_name, filter_project_name):
        "elife projects (and their alternative configurations) that come with the builder pass validation"
        if filter_project_name:
            if project_name != filter_project_name:
                pytest.skip("Filtered out through filter_project_name")

        cfngen.validate_project(project_name)
