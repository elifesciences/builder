import os
from os.path import join
from unittest import TestCase

import logging
LOG = logging.getLogger(__name__)

class BaseCase(TestCase):
    maxDiff = None
    this_dir = os.path.realpath(os.path.dirname(__file__))
    fixtures_dir = join(this_dir, 'fixtures')

    #pyline: disable=invalid-name
    def assertAllPairsEqual(self, fn, pair_lst):
        "given a function and a list of (given, expected) asserts all fn(given) == expected"
        for given, expected in pair_lst:
            try:
                actual = fn(given)
                self.assertEqual(actual, expected)
            except AssertionError:
                LOG.error("failed, %r != %r", expected, actual)
                raise
            except:
                LOG.critical("unexpected failure testing %r", given)
                raise

    #pyline: disable=invalid-name
    def assertAllEqual(self, fn, lst):
        "given a function a list of values, asserts all fn(value) are true"
        for x in lst:
            try:
                y = fn(x)
                self.assertEqual(x, y)
            except AssertionError:
                LOG.error("failed, %r != %r", x, y)
                raise
            except:
                LOG.critical("unexpected failure testing %r", x)
                raise

    #pyline: disable=invalid-name            
    def assertAllNotEqual(self, fn, lst):
        "given a function a list of values, asserts all fn(value) are NOT true"
        for x in lst:
            try:
                y = fn(x)
                self.assertNotEqual(x, y)
            except AssertionError:
                LOG.error("failed, %r == %r", x, y)
                raise
            except:
                LOG.critical("unexpected failure testing %r", x)
                raise
