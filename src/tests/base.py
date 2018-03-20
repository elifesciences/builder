from datetime import datetime
import os
from os.path import join
from subprocess import check_output
from unittest import TestCase
from buildercore import config, project

import logging
import imp
LOG = logging.getLogger(__name__)

class BaseCase(TestCase):
    maxDiff = None
    this_dir = os.path.realpath(os.path.dirname(__file__))
    fixtures_dir = join(this_dir, 'fixtures')

    def __init__(self, *args, **kwargs):
        super(BaseCase, self).__init__(*args, **kwargs)
        self.switch_in_test_settings()

    def switch_in_test_settings(self, new_settings='dummy-settings.yaml'):
        self.original_settings_file = config.SETTINGS_FILE
        config.SETTINGS_FILE = join(self.fixtures_dir, new_settings)
        project.project_map.cache_clear()
        config.app.cache_clear()

    def switch_out_test_settings(self):
        # clear any caches and reload the config module
        project.project_map.cache_clear()
        imp.reload(config)

    def generate_environment_name(self):
        """to avoid multiple people clashing while running their builds
           and new builds clashing with older ones"""
        return check_output('whoami').rstrip().decode() + datetime.utcnow().strftime("%Y%m%d%H%M%S")

    # pyline: disable=invalid-name
    def assertAllPairsEqual(self, fn, pair_lst):
        "given a function and a list of (given, expected) asserts all fn(given) == expected"
        for given, expected in pair_lst:
            with self.subTest(given=given):
                actual = fn(given)
                self.assertEqual(expected, actual, "failed, %r != %r" % (expected, actual))

    # pyline: disable=invalid-name
    def assertAllTrue(self, fn, lst):
        "given a function a list of values, asserts all fn(value) are true"
        for x in lst:
            with self.subTest(given=x):
                self.assertTrue(fn(x), "failed, fn(%s) != True" % x)

    # pyline: disable=invalid-name
    def assertAllNotTrue(self, fn, lst):
        "given a function a list of values, asserts all fn(value) are NOT true"
        for x in lst:
            with self.subTest(given=x):
                self.assertNotEqual(fn(x), "failed, fn(%s) != False" % x)
