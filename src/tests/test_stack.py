import pytest

import stack
import utils


def test_generate_stacks__unknown_stacktype():
    "an error is raised if the given resource type is unsupported."
    with pytest.raises(utils.TaskExit):
        stack.generate_stacks('foo', 'bar')

def test_generate_stacks__unknown_config_file():
    "an error is raised if the given config file doesn't exist"
    with pytest.raises(utils.TaskExit):
        stack.generate_stacks('s3-bucket', '/foo/bar/baz')

# see: src/tests/test_buildercore_project_stack_generation.py
# def test_generate_stacks():
#    stack.generate_stacks('s3-bucket', ...
