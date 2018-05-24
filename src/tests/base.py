from datetime import datetime
import os
from os.path import join
from random import randint
from subprocess import check_output
# pylint: disable-msg=import-error
from unittest2 import TestCase
from buildercore import config, project
import logging
import imp

LOG = logging.getLogger(__name__)

def generate_environment_name():
    """to avoid multiple people clashing while running their builds
       and new builds clashing with older ones"""
    who = check_output('whoami').rstrip().decode()
    now = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return "-".join([who, now, str(randint(1, 1000000))]) # ll: luke-20180420022437-51631

this_dir = os.path.realpath(os.path.dirname(__file__))
fixtures_dir = join(this_dir, 'fixtures')

def switch_in_test_settings(new_settings='dummy-settings.yaml'):
    config.SETTINGS_FILE = join(self.fixtures_dir, new_settings)
    project.project_map.cache_clear()
    config.app.cache_clear()

def switch_out_test_settings(self):
    # clear any caches and reload the config module
    project.project_map.cache_clear()
    imp.reload(config)


class BaseCase(TestCase):
    maxDiff = None

    def __init__(self, *args, **kwargs):
        super(BaseCase, self).__init__(*args, **kwargs)
        switch_in_test_settings()

    # TODO: python2 warning
    def assertCountEqual(self, *args):
        parent = super(BaseCase, self)
        if not hasattr(parent, 'assertCountEqual'):
            self.assertItemsEqual(*args)
        else:
            parent.assertCountEqual(*args)

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
