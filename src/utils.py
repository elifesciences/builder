import os, sys, time
from functools import wraps
import md5
from buildercore import utils as core_utils, cfngen
from datetime import datetime
from buildercore.utils import second, last
from buildercore.decorators import osissue
from fabric.api import run, sudo, local

# totally is assigned :(
#pylint: disable=global-variable-not-assigned
CACHE = {}

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
    return map(lambda ref: last(second(ref).split('/')), _git_remote_refs(url))

def _git_remote_refs(url):
    cmd = "git ls-remote --heads %s" % url
    output = local(cmd, capture=True)
    return map(lambda line: line.split(), output.splitlines())

def errcho(x):
    sys.stderr.write(x)
    sys.stderr.write("\n")
    sys.stderr.flush()
    return x

@osissue("renamed from `_pick` to something. `choose` ?")
def _pick(name, pick_list, default_file=None, helpfn=None):
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
        print
        print 'please pick a known %s:' % name
        for i, pick in enumerate(pick_list):
            print i+1,'-',pick
            if helpfn:
                helptext = helpfn(pick)
                if helptext:
                    print '    "%s"\n' % str(helptext)
        prompt = '> '
        if not default and len(pick_list) == 1:
            default = pick_list[0]
        if default:
            prompt = '> (%r) ' % default
        uinput = get_input(prompt)
        if not uinput or not uinput.lower().strip():
            if default:
                return pick_list[pick_list.index(default)]
            print 'input is required\n'
            continue
        elif not uinput.isdigit() or int(uinput) not in range(1, len(pick_list) + 1):
            print 'a digit within the range of choices is required'
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

def get_input(message):
    return raw_input(message)

def walk_nested_struct(val, fn):
    "walks a potentially nested structure, calling `fn` on each value it encounters"
    if isinstance(val, dict):
        return {key: walk_nested_struct(i, fn) for key, i in val.items()}
    elif isinstance(val, list):
        return [walk_nested_struct(i, fn) for i in val]
    else:
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
            
