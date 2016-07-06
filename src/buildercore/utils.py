import os, sys, copy, json, time, random, string
from functools import wraps
from datetime import datetime
import yaml
from collections import OrderedDict, Iterable
from fabric.api import run
from os.path import join
from more_itertools import unique_everseen
import logging
LOG = logging.getLogger(__name__)

def flatten(l):
    "flattens a single level of nesting [[1] [2] [3]] => [1 2 3]"
    return [item for sublist in l for item in sublist]

def unique(l):
    return list(unique_everseen(l))

def iterable(x):
    return isinstance(x, Iterable)

def conj(x, y):
    "performs a non-mutating update of dict a with the contents of dict b"
    z = copy.deepcopy(x)
    z.update(y)
    return z

def dictfilter(func, ddict):
    "return a subset of dictionary items where func(key, val) is True"
    if not func:
        return ddict
    return {k:v for k, v in ddict.items() if func(k, v)}

def dictmap(func, ddict):
    "apply func over the key+vals of ddict. func should accept two params, key and val."
    return {k:func(k, v) for k, v in ddict.items()}

def subdict(ddict, key_list):
    "returns a version of the given dictionary but only with the keys specified"
    return {k:v for k, v in ddict.items() if k in key_list}

def exsubdict(ddict, key_list):
    "returns a version of the given dictionary with all keys excluding the ones specified"
    return {k:v for k, v in ddict.items() if k not in key_list}

def renkey(ddict, oldkey, newkey):
    "renames a key in ddict from oldkey to newkey"
    if ddict.has_key(oldkey):
        ddict[newkey] = ddict[oldkey]
        del ddict[oldkey]
    return ddict

def complement(pred):
    @wraps(pred)
    def wrapper(*args, **kwargs):
        return not pred(*args, **kwargs)
    return wrapper

def splitfilter(func, data):
    return filter(func, data), filter(complement(func), data)

"""
# NOTE: works, unused.
def deep_exclude(ddict, excluding):
    child_exclude, parent_exclude = splitfilter(lambda v: isinstance(v, dict), excluding)
    child_exclude = first(child_exclude) or {}
    for key, val in ddict.items():
        if key in parent_exclude:
            del ddict[key]
            continue
        if isinstance(val, dict):
            deep_exclude(ddict[key], child_exclude.get(key, []))
"""

def deepmerge(into, from_here, excluding=None):
    "destructive deep merge of `into` with values `from_here`"
    if not excluding:
        excluding = []
    child_exclude, exclusions = splitfilter(lambda v: isinstance(v, dict), excluding)
    child_exclude = first(child_exclude) or {}

    for key in exclusions:
        if key in into and key not in from_here:
            del into[key]
    
    for key, val in from_here.items():
        if into.has_key(key) and isinstance(into[key], dict) \
          and isinstance(val, dict):
            deepmerge(into[key], from_here[key], child_exclude.get(key, []))
        else:
            into[key] = val

def errcho(x):
    "writes the stringified version of x to stderr as a new line"
    sys.stderr.write(x)
    sys.stderr.write("\n")
    sys.stderr.flush()
    return x

def nth(x, n):
    "returns the nth value in x or None"
    try:
        return x[n]
    except (KeyError, IndexError):
        return None
    except TypeError:
        raise

def first(x):
    "returns the first value in x"
    return nth(x, 0)

def second(x):
    "returns the second value in x"
    return nth(x, 1)

def third(x):
    "returns the third value in x"
    return nth(x, 2)

def last(x):
    "returns the last value in x"
    return nth(x, -1)

def rest(x):
    "returns all but the first value in x"
    return x[1:]

def firstnn(x):
    "returns the first non-nil value in x"
    return first(filter(lambda v: v != None, x))
    #return first(filter(None, x))

def cached(func):
    "simple function caching, stores result of calling the function as an attribute. function cannot take args."
    @wraps(func)
    def wrapper():
        ckey = '_cache'
        if hasattr(func, ckey) and not hasattr(func, '_nocache'):
            return getattr(func, ckey)
        result = func()
        setattr(func, ckey, result)
        return result
    return wrapper

def call_while(fn, interval=5, update_msg="waiting ...", done_msg="done."):
    "calls the given function `f` every `interval` until it returns False."
    while True:
        if fn():
            print update_msg
            time.sleep(interval)
        else:
            break
    print done_msg

def call_while_example():
    "a simple example of how to use the `call_while` function. polls fs every two seconds until /tmp/foo is detected"
    def file_doesnt_exist():
        return not os.path.exists("/tmp/foo")
    call_while(file_doesnt_exist, interval=2, update_msg="waiting for /tmp/foo to be created", done_msg="/tmp/foo found")

# deprecated in favour of `lookup` - I prefer `lookup` when no default specified
def getin(data, path):
    "allows dot-path access to nested dicts"
    assert isinstance(data, dict), "getin only works with dictionaries"
    path_bits = path.split('.')
    bit, rest = path_bits[0], path_bits[1:]
    if bit:
        if isinstance(data, dict) and not data.has_key(bit):
            # data not found. return None instead of throwing a fit
            return None
        return getin(data[bit], ".".join(rest))
    # end of path
    return data

def updatein(data, path, newval, create=False):
    """updates a value within a nested dict. use create=True
    to create the path if it doesn't already exist"""
    path_bits = path.split('.')
    bit, rest = path_bits[0], path_bits[1:]
    if not rest:
        # we've come to the end of the path
        data[bit] = newval
        return newval
    if create and not data.has_key(bit):
        data[bit] = {}
    return updatein(data[bit], ".".join(rest), newval, create)

def gget(lst, i, data):
    try:
        return lst[i]
    except IndexError:
        return data

def random_alphanumeric(length=32):
    rand = random.SystemRandom()
    return ''.join(rand.choice(string.ascii_letters + string.digits) for _ in range(length))

# http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts
def ordered_load(stream, loader_class=yaml.Loader, object_pairs_hook=OrderedDict):
    #pylint: disable=no-member
    class OrderedLoader(loader_class):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)

def ordered_dump(data, stream=None, dumper_class=yaml.Dumper, default_flow_style=False, indent=4, line_break='\n', **kwds):
    #pylint: disable=no-member
    class OrderedDumper(dumper_class):
        pass
    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items())
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    kwds.update({'default_flow_style': default_flow_style, 'indent': indent, 'line_break': line_break})
    return yaml.dump(data, stream, OrderedDumper, **kwds)

def remove_ordereddict(data, dangerous=True):
    """turns a nested OrderedDict dict into a regular dictionary. 
    dangerous=True will replace unserializable values with the string '[unserializable]' """
    # so nasty. 
    return json.loads(json_dumps(data, dangerous))

def yaml_to_json(filename):
    "reads the contents of the given yaml file and returns json"
    try:
        return json.dumps(ordered_load(open(filename, 'r')), indent=4)
    except yaml.scanner.ScannerError, ex:
        errcho("Invalid YAML!")
        raise ex

def hasanykey(ddict, key_list):
    return any(map(ddict.has_key, key_list))

def git_purge():
    cmd = 'git reset --hard && git clean -f -d'
    run(cmd)

def listfiles(path, ext_list=None):
    "returns a list of absolute paths for given dir"
    path_list = map(lambda fname: os.path.abspath(join(path, fname)), os.listdir(path))
    if ext_list:
        path_list = filter(lambda path: os.path.splitext(path)[1] in ext_list, path_list)
    return sorted(filter(os.path.isfile, path_list))
    
def git_update():
    cmd = 'git pull --rebase'
    run(cmd)

def ymd(dt=None, fmt="%Y-%m-%d"):
    "formats a datetime object to YYY-mm-dd format"
    if not dt:
        dt = datetime.now()
    return dt.strftime(fmt)

def mkdir_p(path):
    os.system("mkdir -p %s" % path)
    assert os.path.isdir(path), "directory couldn't be created: %s" % path
    assert os.access(path, os.W_OK | os.X_OK), "directory isn't writable: %s" % path
    return path

def json_dumps(obj, dangerous=False):
    """drop-in for json.dumps that handles datetime objects. 
    dangerous=True will replace unserializable values with the string '[unserializable]' """
    def json_handler(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif dangerous:
            return '[unserializable]'
        else:
            raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))
    return json.dumps(obj, default=json_handler)

def lookup(data, path, default=0xDEADBEEF):
    if not isinstance(data, dict):
        raise ValueError("lookup context must be a dictionary")
    if not isinstance(path, basestring):
        raise ValueError("path must be a string, given %r", path)
    try:
        bits = path.split('.', 1)
        if len(bits) > 1:
            bit, rest = bits
        else:
            bit, rest = bits[0], []
        val = data[bit]
        if rest:
            return lookup(val, rest, default)
        return val
    except KeyError:
        if default == 0xDEADBEEF:
            raise
        return default

# TODO: this function suffers from truthy-falsey problems.
#pylint: disable=invalid-name
def lu(context, *paths, **kwargs):
    """looks up many paths given the initial data, returning the first non-nil result.
    if no data available a ValueError is raised."""
    default=None
    if 'default' in kwargs:
        default = kwargs['default']
    v = firstnn(map(lambda path: lookup(context, path, default), paths))
    if v == None:
        raise ValueError("no value available for paths %r. %s" % (paths, context))
    return v

def hasallkeys(ddict, key_list):
    return all(map(ddict.has_key, key_list))
