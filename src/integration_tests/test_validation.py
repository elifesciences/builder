from time import sleep
from tests import base
from buildercore import cfngen, project
import logging
LOG = logging.getLogger(__name__)

# not integration tests per se, but very lengthy and depend on
# talking to AWS.

class TestBuildercoreCfngen(base.BaseCase):

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
            with self.subTest(pname):
                self.assertTrue(cfngen.validate_project(pname))
                sleep(0.5)

        # todo: does this need to live in a try: ... finally: ... ?
        self.switch_in_test_settings()
