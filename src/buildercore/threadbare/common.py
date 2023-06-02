import os
from functools import reduce


class PromptedException(BaseException):
    pass


def ensure(assertion, msg, exception_class=AssertionError):
    """intended as a convenient replacement for `assert` statements that
    gets compiled away with the `-O` flag."""
    if not assertion:
        raise exception_class(msg)


def first(x):
    "returns the first element in a collection or `None`."
    if x is None:
        return x
    try:
        return x[0]
    except IndexError:
        return None
    except (ValueError, KeyError):
        raise


def merge(*dict_list):
    "non-destructively merges a series of dictionaries from left to right, returning a new dictionary."

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
def _shell_escape(string):
    """
    Escape double quotes, backticks and dollar signs in given ``string``.
    For example::
        >>> _shell_escape('abc$')
        'abc\\\\$'
        >>> _shell_escape('"')
        '\\\\"'
    """

    ensure(string is not None, "a string is required", TypeError)

    for char in ('"', "$", "`"):
        string = string.replace(char, r"\%s" % char)
    return string


# https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L253-L256
def shell_wrap_command(command):
    """wraps the given command in a shell invocation.
    default shell is /bin/bash (like Fabric)
    no support for configurable shell at present"""

    # '-l' is 'login' shell
    # '-c' is 'run command'
    shell_prefix = "/bin/bash -l -c"

    escaped_command = _shell_escape(command)
    escaped_wrapped_command = '"%s"' % escaped_command

    return "%s %s" % (shell_prefix, escaped_wrapped_command)


def sudo_wrap_command(command):
    """adds a 'sudo' prefix to command to run as root.
    no support for sudo'ing to configurable users/groups"""
    # https://github.com/mathiasertl/fabric/blob/master/fabric/operations.py#L605-L623
    # https://github.com/mathiasertl/fabric/blob/master/fabric/state.py#L374-L376
    # note: differs from Fabric. they support interactive input of password, users and groups
    # we use it exclusively to run commands as root

    sudo_prefix = "sudo --non-interactive"
    return "%s %s" % (sudo_prefix, command)


def cwd_wrap_command(command, working_dir):
    "adds a 'cd' prefix to command"

    prefix = 'cd "%s" &&' % working_dir
    return "%s %s" % (prefix, command)


def isint(x):
    try:
        int(x)
        return True
    except BaseException:
        return False
