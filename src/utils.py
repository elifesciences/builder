import logging
import os, sys
from distutils.util import strtobool as _strtobool  # pylint: disable=import-error,no-name-in-module
from buildercore import config
from buildercore.utils import second, last, gtpy2
from buildercore.command import local
from buildercore import core

LOG = logging.getLogger(__name__)

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
        try:
            lst.remove(val)
            removed.append(val)
        except ValueError:
            continue
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
    fn = input if gtpy2() else raw_input
    return fn(message)

def _pick(name, pick_list, default_file=None, helpfn=None, message='please pick:'):
    default = None
    if default_file:
        try:
            default = open(default_file, 'r').read()
            pick_list.index(default)
        except (ValueError, IOError):
            # either the given default file doesn't exist or the
            # default value doesn't appear in pick list, ignore given default
            default = None
    while True:
        print("%s (%s)" % (message, name))
        for i, pick in enumerate(pick_list):
            print(i + 1, '-', pick)
            if helpfn:
                helptext = helpfn(pick)
                if helptext:
                    print('    "%s"\n' % str(helptext))
        prompt = '> '
        if not default and len(pick_list) == 1:
            default = pick_list[0]
        if default:
            prompt = '> (%r) ' % default
        uinput = get_input(prompt)
        if not uinput or not uinput.lower().strip():
            if default:
                return pick_list[pick_list.index(default)]
            print('input is required\n')
            continue
        elif not uinput.isdigit() or int(uinput) not in list(range(1, len(pick_list) + 1)):
            print('a digit within the range of choices is required')
            continue
        choice = pick_list[int(uinput) - 1]
        if default_file:
            # write the new default to file
            open(default_file, 'w').write(choice)
        return choice

def uin(param, default=0xDEADBEEF):
    while True:
        if default and default != 0xDEADBEEF:
            errcho("%s [%s]: " % (param, default))
        else:
            errcho(param + ':')
        userin = get_input('> ')
        if not userin or not userin.strip():
            if default != 0xDEADBEEF:
                return default
            errcho('input is required (ctrl-c to quit)')
            continue
        return userin


def confirm(message):
    if config.BUILDER_NON_INTERACTIVE:
        LOG.info('Non-interactive mode, confirming automatically')
        return

    errcho(message)
    errcho('press Enter to confirm (ctrl-c to quit)')
    get_input('')

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

def table(rows, keys):
    lines = []
    for row in rows:
        lines.append(', '.join([getattr(row, key) for key in keys]))
    return "\n".join(lines)

def find_region(stackname=None):
    """tries to find the region, but falls back to user input if there are multiple regions available.
    Uses stackname, if provided, to filter the available regions"""
    try:
        return core.find_region(stackname)
    except core.MultipleRegionsError as e:
        print("many possible regions found!")
        return _pick('region', e.regions())
