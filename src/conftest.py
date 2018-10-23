import pytest
from buildercore.config import get_logger

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
