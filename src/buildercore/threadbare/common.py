import six
import os
from functools import reduce


class PromptedException(BaseException):
    pass


def has_type(x, t, msg=None):
    "raises TypeError if given `x` is not of type `t`"
    msg = msg or "%r is not of expected type %r" % (x, t)
    if t == str and not isinstance(x, six.string_types):
        raise TypeError(msg)

    if not isinstance(x, t):
        raise TypeError(msg)


def all_have_type(pair_list, msg=None):
    "raises TypeError if any x in pair (x, t) in `pair_list` is not of type `t`"
    has_type(pair_list, list)
    for x, t in pair_list:
        has_type(x, t, msg)


def first(x):
    "returns the first element in an collection of things"
    if x is None:
        return x
    try:
        return x[0]
    except IndexError:
        return None
    except (ValueError, KeyError):
        raise


def merge(*dict_list):
    "non-destructively merges a series of dictionaries from left to right, returning a new dictionary"

    def reduce_fn(d1, d2=None):
        d3 = {}
        d3.update(d1)
        d3.update(d2 or {})
        return d3

    return reduce(reduce_fn, dict_list)


def subdict(d, key_list):
    "returns a subset of the given dictionary `d` for keys in `key_list`"
    key_list = key_list or []
    return {key: d[key] for key in key_list if key in d}


def rename(d, pair_list):
    "mutator. given a dictionary `d` and a list of (old-name, new-name) pairs, renames old-name to new-name, if it exists"
    for old, new in pair_list:
        if old in d:
            d[new] = d[old]
            del d[old]


def cwd():
    "returns the resolved path to the Current Working Dir (cwd)"
    return os.path.realpath(os.curdir)


# utils

# direct copy from Fabric:
# https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L33-L46
# TODO: adjust licence accordingly
def _shell_escape(string):
    """
    Escape double quotes, backticks and dollar signs in given ``string``.
    For example::
        >>> _shell_escape('abc$')
        'abc\\\\$'
        >>> _shell_escape('"')
        '\\\\"'
    """

    has_type(string, str)

    for char in ('"', "$", "`"):
        string = string.replace(char, r"\%s" % char)
    return string


# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L253-L256
def shell_wrap_command(command):
    """wraps the given command in a shell invocation.
    default shell is /bin/bash (like Fabric)
    no support for configurable shell at present"""

    has_type(command, str)

    # '-l' is 'login' shell
    # '-c' is 'run command'
    shell_prefix = "/bin/bash -l -c"

    escaped_command = _shell_escape(command)
    escaped_wrapped_command = '"%s"' % escaped_command

    space = " "
    final_command = shell_prefix + space + escaped_wrapped_command

    return final_command


def sudo_wrap_command(command):
    """adds a 'sudo' prefix to command to run as root.
    no support for sudo'ing to configurable users/groups"""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L605-L623
    # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L374-L376
    # note: differs from Fabric. they support interactive input of password, users and groups
    # we use it exclusively to run commands as root

    has_type(command, str)

    sudo_prefix = "sudo --non-interactive"
    space = " "
    return sudo_prefix + space + command


def cwd_wrap_command(command, working_dir):
    "adds a 'cd' prefix to command"

    all_have_type([(command, str), (working_dir, str)])

    prefix = 'cd "%s" &&' % working_dir
    space = " "
    return prefix + space + command


def isint(x):
    try:
        int(x)
        return True
    except BaseException:
        return False
