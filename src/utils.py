import os, sys, time
from functools import wraps
import md5
from buildercore import utils as core_utils, cfngen
from datetime import datetime
from buildercore.utils import second, last
from fabric.api import run, sudo, local

# totally is assigned :(
#pylint: disable=global-variable-not-assigned
CACHE = {}

# deprecated. use buildercore.utils.splitfilter
@osissue("emabarassing code. remove/replace")
def splitfilter(fn, lst):
    l1, l2 = [], []
    for x in lst:
        (l1 if fn(x) else l2).append(x)
    return l1, l2

@osissue("duplicate code")
def git_purge(as_sudo=False):
    cmd = 'git reset --hard && git clean -f -d'
    if as_sudo:
        return sudo(cmd)
    return run(cmd)

@osissue("duplicate code")
def git_update():
    cmd = 'git pull --rebase'
    run(cmd)

def git_remote_refs(url):
    cmd = "git ls-remote --heads %s" % url
    output = local(cmd, capture=True)
    return map(lambda line: line.split(), output.splitlines())

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
    return map(lambda ref: last(second(ref).split('/')), git_remote_refs(url))

def just_one(lst):
    "use this when you're given a list and you only ever expect a single result"
    assert len(lst) == 1, 'expecting just a single result. multiple results indicates a potential problem %r' % lst
    return lst[0]

def errcho(x):
    sys.stderr.write(x)
    sys.stderr.write("\n")
    sys.stderr.flush()
    return x

@osissue("emabarassing code. remove/replace")
def cached(func):
    @wraps(func)
    def wrapper(*args):
        global CACHE
        key = func.__name__
        if args: # not recommended
            key += md5.md5(str(args)).hexdigest()
        if CACHE.get(key):
            return CACHE[key]
        result = func(*args)
        CACHE[key] = result
        return result
    return wrapper

@osissue("unusued/duplicate code. see `buildercore.utils:call_while`")
def call_until(func, pred, sleep_duration=2, output_interval=5, msg=None):
    "calls `func` until pred(func()) is true. outputs time after every `output_interval`"
    start_time = time.time()
    i = 0
    te = 0
    last_output = 0
    while True:
        try:
            res = func()
            if pred(res):
                return res # success, exit loop            
        except Exception:
            raise

        if i == 0:
            if msg:
                print msg
            #sys.stdout.write('waiting ')
        
        sys.stdout.write('.')
        te = time.time() - start_time
        if int(te / output_interval) > last_output:
            last_output = int(te / output_interval)
            sys.stdout.write(" %ss " % str(int(te)))
        sys.stdout.flush()
        i += 1
        time.sleep(sleep_duration)
    print

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
        uinput = raw_input(prompt)
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
        userin = raw_input('> ')
        if not userin or not userin.strip():
            if default != 0xDEADBEEF:
                return default
            errcho('input is required (ctrl-c to quit)')
            continue
        return userin

@osissue("references salt. refactor")    
def salt_pillar_data():
    return cfngen.salt_pillar_data('salt/pillar/')

@osissue("refactor. one of about three implementations.")
def getin(data, path):
    "allows dot-path access to nested dicts"
    path_bits = path.split('.')
    bit, rest = path_bits[0],path_bits[1:]
    if bit:
        if isinstance(data, dict) and not data.has_key(bit):
            # data not found. return None instead of throwing a fit
            return None
        return getin(data[bit], ".".join(rest))
    # end of path
    return data
        
def updatein(data, path, newval):
    path_bits = path.split('.')
    bit, rest = path_bits[0],path_bits[1:]
    if not rest:
        # we've come to the end of the path
        data[bit] = newval
        return newval
    return updatein(data[bit], ".".join(rest), newval)

def walk_nested_struct(val, fn):
    "walks a potentially nested structure, calling `fn` on each value it encounters"
    if isinstance(val, dict):
        return {key: walk_nested_struct(i, fn) for key, i in val.items()}
    elif isinstance(val, list):
        return [walk_nested_struct(i, fn) for i in val]
    else:
        return fn(val)

# DEPRECATED: use core_utils.lookup
def resolve_dotted(data, path, defaults=0xDEADBEEF):
    return core_utils.lookup(data, path, defaults)

def mkdirp(path):
    return os.system("mkdir -p %s" % path) == 0

def pwd():
    return os.path.dirname(os.path.realpath(__file__))

@osissue("not being used. handy code reference though")
def system(cmd):
    "executes given cmd as a subprocess, waits for cmd to finish and returns a triple of (return code, stdout, stderr)"
    print 'attempting to execute %r in %r' % (cmd, pwd())
    from subprocess import PIPE, Popen
    child = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = child.communicate()
    return child.returncode, stdout, stderr
