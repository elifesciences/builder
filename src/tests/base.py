from datetime import datetime
import json
import logging
import os
from os.path import join
from random import randint
from subprocess import check_output
# pylint: disable-msg=import-error
from unittest2 import TestCase
from buildercore.command import settings
from buildercore import config, project
from buildercore import bootstrap, cfngen, lifecycle, core
import cfn
import imp
#import pytest # see ../conftest.py

LOG = logging.getLogger(__name__)

def generate_environment_name():
    """to avoid multiple people clashing while running their builds
       and new builds clashing with older ones"""
    who = check_output('whoami').rstrip().decode()
    now = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return "-".join([who, now, str(randint(1, 1000000))]) # ll: luke-20180420022437-51631

this_dir = os.path.realpath(os.path.dirname(__file__))
fixtures_dir = join(this_dir, 'fixtures')

def switch_in_test_settings(projects_files=None):
    if not projects_files:
        projects_files = ['src/tests/fixtures/projects/']
    config.PROJECTS_FILES = projects_files
    project.project_map.cache_clear()
    config.app.cache_clear()

def switch_out_test_settings():
    # clear any caches and reload the config module
    project.project_map.cache_clear()
    imp.reload(config)

def test_project_list():
    switch_in_test_settings()
    return project.aws_projects().keys()

def elife_project_list():
    switch_out_test_settings()
    return project.aws_projects().keys()

class BaseCase(TestCase):
    maxDiff = None

    def __init__(self, *args, **kwargs):
        super(BaseCase, self).__init__(*args, **kwargs)
        switch_in_test_settings()
        self.fixtures_dir = fixtures_dir

    # TODO: python2 warning
    # pylint: disable=E1101
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

class BaseIntegrationCase(BaseCase):
    @classmethod
    def set_up_stack(cls, project, explicitly_start=False):
        switch_in_test_settings()

        # to re-use an existing stack, ensure cls.reuse_existing_stack is True
        # this will read the instance name from a temporary file (if it exists) and
        # look for that, creating it if doesn't exist yet
        # also ensure cls.cleanup is False so the instance isn't destroyed after tests complete
        cls.reuse_existing_stack = config.TWI_REUSE_STACK
        cls.cleanup = config.TWI_CLEANUP

        cls.stacknames = []
        cls.environment = generate_environment_name()
        # cls.temp_dir, cls.rm_temp_dir = utils.tempdir()

        # debugging only, where we keep an instance up between processes
        cls.state, cls.statefile = {}, '/tmp/.open-test-instances.txt'

        if cls.reuse_existing_stack and os.path.exists(cls.statefile):
            # evidence of a previous instance and we've been told to re-use old instances
            old_state = json.load(open(cls.statefile, 'r'))
            old_env = old_state.get('environment')

            # test if the old stack still exists ...
            if old_env and core.describe_stack(project + "--" + old_env, allow_missing=True):
                cls.state = old_state
                cls.environment = old_env
            else:
                # nope. old statefile is bogus, delete it
                os.unlink(cls.statefile)

        cls.state['environment'] = cls.environment # will be saved later

        with settings(abort_on_prompts=True):
            cls.stackname = '%s--%s' % (project, cls.environment)
            cls.stacknames.append(cls.stackname)

            if cls.cleanup:
                LOG.info("ensure_destroyed %s", cls.stackname)
                cfn.ensure_destroyed(cls.stackname)

            cls.context, cls.cfn_template, _ = cfngen.generate_stack(project, stackname=cls.stackname)
            cls.region = cls.context['aws']['region']
            LOG.info("create_stack %s", cls.stackname)
            bootstrap.create_stack(cls.stackname)

            if explicitly_start:
                LOG.info("start %s", cls.stackname)
                lifecycle.start(cls.stackname)

    @classmethod
    def tear_down_stack(cls):
        try:
            if cls.reuse_existing_stack:
                json.dump(cls.state, open(cls.statefile, 'w'))
            if cls.cleanup:
                for stackname in cls.stacknames:
                    LOG.info("ensure_destroyed %s", stackname)
                    cfn.ensure_destroyed(stackname)
            # cls.rm_temp_dir()
            # cls.assertFalse(os.path.exists(cls.temp_dir), "failed to delete path %r in tearDown" % cls.temp_dir)
        except BaseException:
            # important, as anything in body will silently fail
            LOG.exception('uncaught error tearing down test class')
