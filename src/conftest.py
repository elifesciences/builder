import pytest

def pytest_addoption(parser):
    parser.addoption("--filter-project-name",
            action="store",
            default=None,
            help="pass a project name to filter a test file to run only tests related to it")

@pytest.fixture
def filter_project_name(request):
    return request.config.getoption('--filter-project-name')
