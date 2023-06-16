"""Test fixtures made available via decorators during the test run.

The `conftest.py` file is a barely documented pytest-ism.
pytest will look for this file and execute it's contents automatically.

In this file we're defining globally available test fixtures that are injected magically using parameter
name matching alone. For example:

    def test_foo(bar, baz):
        ...

will have the results of calling the `bar` fixture passed as the first parameter and the
results of calling the `baz` fixture passed as the second parameter.

https://stackoverflow.com/questions/34466027/in-pytest-what-is-the-use-of-conftest-py-files
https://docs.pytest.org/en/latest/writing_plugins.html#conftest-py-plugins
https://docs.pytest.org/en/stable/fixture.html#factories-as-fixtures"""

import logging
import pytest
from buildercore.utils import tempdir as core_utils_tempdir
from buildercore.config import get_logger, CONSOLE_HANDLER
from tests import base
from unittest import mock

CONSOLE_HANDLER.setLevel(logging.CRITICAL)

LOG = get_logger("conftest")

def pytest_addoption(parser):
    parser.addoption("--filter-project-name",
                     action="store",
                     default=None,
                     help="pass a project name to filter a test file to run only tests related to it")

@pytest.fixture
def filter_project_name(request):
    return request.config.getoption('--filter-project-name')

def pytest_runtest_setup(item):
    LOG.info("Setting up %s::%s", item.cls, item.name)

def pytest_runtest_teardown(item, nextitem):
    LOG.info("Tearing down up %s::%s", item.cls, item.name)

# https://docs.pytest.org/en/7.1.x/how-to/fixtures.html#fixture-scopes
@pytest.fixture(scope='session')
def test_projects():
    try:
        base.switch_in_test_settings()
        yield
    finally:
        base.switch_out_test_settings()

@pytest.fixture
def tempdir():
    "replaces the path to `/tmp` with a unique temp directory for the age of the test."
    path, cleanup_fn = core_utils_tempdir()
    try:
        with mock.patch('tempfile.gettempdir', return_value=path):
            yield path
    finally:
        cleanup_fn()

@pytest.fixture
def datadir():
    "returns a path to a unique temp directory for the age of the test."
    path, cleanup_fn = core_utils_tempdir()
    try:
        yield path
    finally:
        cleanup_fn()
