import utils
import stack
import pytest

def test_generate_stacks__unknown_stacktype():
    "an error is raised if the given resource type is unsupported."
    with pytest.raises(utils.TaskExit):
        stack.generate_stack_data_file('foo', 'bar')

def test_generate_stacks__unknown_config_file():
    "an error is raised if the given config file doesn't exist"
    with pytest.raises(utils.TaskExit):
        stack.generate_stack_data_file('s3-bucket', '/foo/bar/baz')
