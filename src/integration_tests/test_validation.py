import pytest
from tests import base
from buildercore import cfngen
import logging
LOG = logging.getLogger(__name__)

logging.disable(logging.NOTSET) # re-enables logging during integration testing

# Depends on talking to AWS.

class TestValidationFixtures():
    @classmethod
    def setup_class(cls):
        base.switch_in_test_settings()

    @pytest.mark.parametrize("project_name", base.test_project_list())
    def test_validation(self, project_name):
        "dummy projects and their alternative configurations pass validation"
        cfngen.validate_project(project_name)

class TestValidationElife():
    @classmethod
    def setup_class(cls):
        base.switch_out_test_settings()

    @classmethod
    def teardown_class(cls):
        base.switch_in_test_settings()

    @pytest.mark.parametrize("project_name", base.elife_project_list())
    def test_validation_elife_projects(self, project_name, filter_project_name):
        "elife projects (and their alternative configurations) that come with the builder pass validation"
        if filter_project_name:
            if project_name != filter_project_name:
                pytest.skip("Filtered out through filter_project_name")

        cfngen.validate_project(project_name)
