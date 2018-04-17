from tests import base
from buildercore import cfngen, project
import logging
LOG = logging.getLogger(__name__)

logging.disable(logging.NOTSET) # re-enables logging during integration testing

# Depends on talking to AWS.

class TestValidation(base.BaseCase):

    def test_validation(self):
        "dummy projects and their alternative configurations pass validation"
        for pname in project.aws_projects().keys():
            cfngen.validate_project(pname)

    def test_validation_elife_projects(self):
        "elife projects (and their alternative configurations) that come with the builder pass validation"

        # HERE BE DRAGONS
        # resets the testing config.SETTINGS_FILE we set in the base.BaseCase class
        self.switch_out_test_settings()

        for pname in project.aws_projects().keys():
            with self.subTest(pname):
                cfngen.validate_project(pname)

        # todo: does this need to live in a try: ... finally: ... ?
        self.switch_in_test_settings()
