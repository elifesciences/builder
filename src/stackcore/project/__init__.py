from buildercore import utils, config, project
from . import stack_config
# import logging
from functools import reduce

# LOG = logging.getLogger(__name__)

def _stack_map(path_list=None, stackname=None):
    """returns a single map of all projects and their data"""

    path_list = path_list or config.STACKS_PATH_LIST

    # a list of paths
    # ['/path/to/projects.yaml', ...]
    path_list = project.parse_path_list(path_list)

    # a list of parsed project data:
    # [{'/path/to/stack.yaml': {'stack1': {...}, 'stack2': {...}, ...}, {'/path/to/another-stack.yaml': {...}}, ...]
    if stackname:
        # ignore all other stacks when a specific stackname has been given.
        data = [{path: stack_config.stack_data(stackname, path)} for path in path_list]
    else:
        data = [{path: stack_config.all_stack_data(path)} for path in path_list]

    # a single map of paths to parsed project data
    # {'/path/to/stack.yaml': {'stack1': {...}, 'stack2': {...}, ...}, '/path/to/another-stacks.yaml': {...}, ...}
    data = reduce(utils.merge, data, {})

    # a list of parsed stack data.
    # [{'stack1': {...}, 'stack2': {...}, ...}, {...}, ...]
    data = data.values()

    # a single map of parsed stack data.
    # {'stack1': {...}, 'stack2': {...}, ...}
    # note: if you have two stacks with the same name in different files, one will replace the other.
    # precedence depends on order of paths in given `project_locations_list`, earlier paths are overridden by later.
    return reduce(utils.merge, data, {})

def stack_map(path_list=None):
    "returns a single map of all stacks and their data."
    return _stack_map(path_list)

def stack(stackname, path_list=None):
    "returns a single map of a single stack and it's data."
    return _stack_map(path_list, stackname)
