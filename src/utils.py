import logging
import os
import sys
from distutils.util import strtobool as _strtobool

from buildercore import config, core
from buildercore.command import local
from buildercore.utils import ensure, isint, last, second

LOG = logging.getLogger(__name__)

# added 2021-06
# see `taskrunner.exec_task` for handling of tasks that raise this.
class TaskExit(BaseException):
    "raise to quit a task early"

def strtobool(x):
    """wraps `distutils.util.strtobool` that casts 'yes', 'no', '1', '0', 'true', 'false', etc to
    boolean values, but only if the given value isn't already a boolean"""
    return x if isinstance(x, bool) else bool(_strtobool(str(x)))

def rmval(lst, *vals):
    """removes each val in `vals` from `lst`, if it exists.
    returns new `lst` and a list of removed values in the order they were removed."""
    lst = lst[:]
    removed = []
    for val in vals:
        if val in lst:
            lst.remove(val)
            removed.append(val)
    return lst, removed

def git_remote_branches(url):
    # in: [('asdf', 'refs/heads/develop'), ('fdas', 'refs/heads/master',) ...]
    # out: ['develop', 'master', ...]
    return [last(second(ref).split('/')) for ref in _git_remote_refs(url)]

def _git_remote_refs(url):
    cmd = "git ls-remote --heads %s" % url
    output = local(cmd, capture=True)['stdout']
    return [line.split() for line in output]

def errcho(x):
    sys.stderr.write(x)
    sys.stderr.write("\n")
    sys.stderr.flush()
    return x

def get_input(message):
    """previously a wrapper around the py2 `raw_input` vs py3 `input` builtins,
    it now serves as a single place to read from stdin and enforce `config.BUILDER_NON_INTERACTIVE`."""
    ensure(not config.BUILDER_NON_INTERACTIVE, "stdin requested in non-interactive mode.", IOError)
    return input(message)

def _pick(name, pick_list, default_file=None, helpfn=None, message='please pick:'):
    default = None
    if default_file:
        try:
            with open(default_file) as fh:
                default = fh.read()
            pick_list.index(default)
        except (OSError, ValueError):
            # either the given default file doesn't exist or the
            # default value doesn't appear in pick list, ignore given default
            default = None
    while True:
        errcho("%s (%s)" % (message, name))
        for i, pick in enumerate(pick_list):
            errcho("%s - %s" % (i + 1, pick))
            if helpfn:
                helptext = helpfn(pick)
                if helptext:
                    errcho('    "%s"\n' % str(helptext))
        prompt = '> '
        if not default and len(pick_list) == 1:
            default = pick_list[0]
        if default:
            prompt = '> (%r) ' % default
        uinput = get_input(prompt)
        if not uinput or not uinput.lower().strip():
            if default:
                return pick_list[pick_list.index(default)]
            errcho('input is required\n')
            continue
        if not uinput.isdigit() or int(uinput) not in list(range(1, len(pick_list) + 1)):
            errcho('a digit within the range of choices is required')
            continue
        choice = pick_list[int(uinput) - 1]
        if default_file:
            # write the new default to file
            with open(default_file, 'w') as fh:
                fh.write(choice)
        return choice

def uin(param, default=0xDEADBEEF):
    "a slightly fancier `get_input` that allows a default value and keeps prompting until it has *something*."
    improbable_default = 0xDEADBEEF
    if config.BUILDER_NON_INTERACTIVE:
        ensure(default != improbable_default, "stdin requested in non-interactive mode with no default.")
        LOG.warning("non-interactive mode, returning default '%s'.", default)
        return default

    while True:
        if default and default != improbable_default:
            errcho("%s [%s]: " % (param, default))
        else:
            errcho("%s: " % param)
        userin = get_input('> ')
        if not userin or not userin.strip():
            if default != improbable_default:
                return default
            errcho('input is required (ctrl-c to quit)')
            continue
        return userin


def confirm(message, type_to_confirm=None):
    if config.BUILDER_NON_INTERACTIVE:
        LOG.info('non-interactive mode, confirming automatically')
        return True

    errcho(message)
    if not type_to_confirm:
        errcho('press Enter to confirm (ctrl-c to quit)')
        get_input('')
        return True

    errcho('type %r to continue (ctrl-c to quit)\n' % type_to_confirm)
    uinput = get_input('> ')
    errcho('')
    return uinput == type_to_confirm

def walk_nested_struct(val, fn):
    "walks a potentially nested structure, calling `fn` on each value it encounters"
    if isinstance(val, dict):
        return {key: walk_nested_struct(i, fn) for key, i in val.items()}
    if isinstance(val, list):
        return [walk_nested_struct(i, fn) for i in val]
    return fn(val)

def mkdirp(path):
    return os.system("mkdir -p %s" % path) == 0

def pwd():
    return os.path.dirname(os.path.realpath(__file__))

def find_region(stackname=None):
    """tries to find the region, but falls back to user input if there are multiple regions available.
    Uses stackname, if provided, to filter the available regions"""
    try:
        return core.find_region(stackname)
    except core.MultipleRegionsError as e:
        errcho("many possible regions found!")
        return _pick('region', e.regions())

def coerce_string_value(value_str):
    """attempts to coerce given `value_str` to a None, then a boolean, then an integer, returning the given value if coercion not possible.
    non-string values are returned immediately."""
    if not isinstance(value_str, str):
        return value_str

    none_list = ["", "none", "null", "nil"]
    bool_list = ["false", "true"]

    vlow = value_str.lower().strip()
    if vlow in none_list:
        return None

    if vlow in bool_list:
        return vlow == "true"

    if isint(vlow):
        return int(vlow)

    return value_str
