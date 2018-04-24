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
            # TODO: subTest doesn't work very well here because there's no way to filter a single pname when re-running after a failure
            # a solution like
            # https://github.com/elifesciences/elife-spectrum/blob/master/spectrum/test_article.py#L15-L19
            # could help, but require to run tests with pytest only
            with self.subTest(pname):
                cfngen.validate_project(pname)

        # todo: does this need to live in a try: ... finally: ... ?
        self.switch_in_test_settings()
