import importlib
import json
import logging
import os
import shutil
from os.path import join
from random import randint
from subprocess import check_output
from unittest import TestCase

import cfn
from buildercore import bootstrap, cfngen, config, core, lifecycle, project, utils
from buildercore.command import settings

# import pytest # see ../conftest.py

LOG = logging.getLogger(__name__)

def set_config(key, value):
    """modify configuration values in `buildercore/config.py`.
    returns a cleanup function to call in `tearDown` that will reset the value.
    IMPORTANT! modules have to do:
      `import config`
    and then:
      `config.SOME_VAR`
    and not:
      `from config import SOME_VAR`
    or this magic won't work."""
    old_value = getattr(config, key, None)
    setattr(config, key, value)
    return lambda: setattr(config, key, old_value)

def generate_environment_name():
    """to avoid multiple people clashing while running their builds
       and new builds clashing with older ones"""
    who = check_output('whoami').rstrip().decode()
    now = utils.utcnow().strftime("%Y%m%d%H%M%S")
    return "-".join([who, now, str(randint(1, 1000000))]) # "luke-20180420022437-51631"

this_dir = os.path.realpath(os.path.dirname(__file__))
fixtures_dir = join(this_dir, 'fixtures')

def fixture_path(fixture_subpath):
    "returns full path to given fixture"
    return os.path.join(fixtures_dir, fixture_subpath)

def fixture(fixture_subpath):
    "returns contents of given fixture as a string"
    with open(fixture_path(fixture_subpath)) as fh:
        return fh.read()

def json_fixture(fixture_subpath):
    "same as `fixture`, but deserialises the contents from JSON."
    return json.loads(fixture(fixture_subpath))

def copy_fixture(fixture_subpath, destination_path):
    """copies the fixture as `fixture_subpath` to the `destination_path`.
    if `destination_path` is *not* a directory, the fixture will be renamed."""
    if os.path.isdir(destination_path):
        # /tmp => /tmp/foo.bar
        destination_path = os.path.join(destination_path, os.path.basename(fixture_subpath))
    shutil.copyfile(fixture_path(fixture_subpath), destination_path)
    return destination_path

def switch_in_test_settings(projects_files=None):
    if not projects_files:
        projects_files = ['src/tests/fixtures/projects/']
    config.PROJECTS_PATH_LIST = projects_files
    # lsh@2023-03-31: set as default. see the `test_utils.test_uin__*` tests on how to override this.
    config.BUILDER_NON_INTERACTIVE = True
    # lsh@2021-06-22: may not be necessary any more.
    # project_map now returns a deepcopy of cached results.
    project._project_map.cache_clear()

def switch_out_test_settings():
    # clear any caches and reload the config module
    project._project_map.cache_clear()
    importlib.reload(config)

def test_project_list():
    switch_in_test_settings()
    return project.aws_projects().keys()

def elife_project_list():
    switch_out_test_settings()
    return project.aws_projects().keys()

class BaseCase(TestCase):
    maxDiff = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        switch_in_test_settings()
        self.fixtures_dir = fixtures_dir

    def assertCountEqual(self, *args): # noqa: N802
        parent = super()
        if not hasattr(parent, 'assertCountEqual'):
            self.assertItemsEqual(*args)
        else:
            parent.assertCountEqual(*args)

    def assertAllPairsEqual(self, fn, pair_lst): # noqa: N802
        "given a function and a list of (given, expected) asserts all fn(given) == expected"
        for given, expected in pair_lst:
            with self.subTest(given=given):
                actual = fn(given)
                self.assertEqual(expected, actual, "failed, %r != %r" % (expected, actual))

    def assertAllTrue(self, fn, lst): # noqa: N802
        "given a function a list of values, asserts all fn(value) are true"
        for x in lst:
            with self.subTest(given=x):
                self.assertTrue(fn(x), "failed, fn(%s) != True" % x)

    def assertAllNotTrue(self, fn, lst): # noqa: N802
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
            with open(cls.statefile) as fh:
                old_state = json.load(fh)
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
                with open(cls.statefile, 'w') as fh:
                    json.dump(cls.state, fh)
            if cls.cleanup:
                for stackname in cls.stacknames:
                    LOG.info("ensure_destroyed %s", stackname)
                    cfn.ensure_destroyed(stackname)
            # cls.rm_temp_dir()
            # cls.assertFalse(os.path.exists(cls.temp_dir), "failed to delete path %r in tearDown" % cls.temp_dir)
        except BaseException:
            # important, as anything in body will silently fail
            LOG.exception('uncaught error tearing down test class')
