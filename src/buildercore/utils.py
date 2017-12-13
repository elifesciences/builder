import pytz
import os, sys, copy, json, time, random, string
from StringIO import StringIO
from functools import wraps
from datetime import datetime
import yaml
from collections import OrderedDict, Iterable
from os.path import join
from more_itertools import unique_everseen

import logging
LOG = logging.getLogger(__name__)

def shallow_flatten(lst):
    "flattens a single level of nesting [[1] [2] [3]] => [1 2 3]"
    return [item for sublist in lst for item in sublist]

def unique(lst):
    return list(unique_everseen(lst))

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
    return {k: v for k, v in ddict.items() if func(k, v)}

def dictmap(fn, ddict):
    return {key: fn(key, val) for key, val in ddict.items()}

def subdict(ddict, key_list):
    return {k: v for k, v in ddict.items() if k in key_list}

def exsubdict(ddict, key_list):
    "returns a version of the given dictionary excluding the keys specified"
    return {k: v for k, v in ddict.items() if k not in key_list}

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
        if key in into and isinstance(into[key], dict) \
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

def firstnn(x):
    "returns the first non-nil value in x"
    return first(filter(lambda v: v is not None, x))
    # return first(filter(None, x))

# pylint: disable=too-many-arguments
def call_while(fn, interval=5, timeout=600, update_msg="waiting ...", done_msg="done.", exception_class=None):
    "calls the given function `f` every `interval` until it returns False."
    if not exception_class:
        exception_class = RuntimeError
    elapsed = 0
    while True:
        if not fn():
            break
        if elapsed >= timeout:
            raise exception_class("Reached timeout %d while %s" % (timeout, update_msg))
        LOG.info(update_msg)
        time.sleep(interval)
        elapsed = elapsed + interval
    LOG.info(done_msg)

def call_while_example():
    "a simple example of how to use the `call_while` function. polls fs every two seconds until /tmp/foo is detected"
    def file_doesnt_exist():
        return not os.path.exists("/tmp/foo")
    call_while(file_doesnt_exist, interval=2, update_msg="waiting for /tmp/foo to be created", done_msg="/tmp/foo found")

def updatein(data, path, newval, create=False):
    """updates a value within a nested dict. use create=True
    to create the path if it doesn't already exist"""
    path_bits = path.split('.')
    bit, rest = path_bits[0], path_bits[1:]
    if not rest:
        # we've come to the end of the path
        data[bit] = newval
        return newval
    if create and bit not in data:
        data[bit] = {}
    return updatein(data[bit], ".".join(rest), newval, create)

def random_alphanumeric(length=32):
    rand = random.SystemRandom()
    return ''.join(rand.choice(string.ascii_letters + string.digits) for _ in range(length))


'''
# works, but the !include function is unused
def yaml_load(stream):
    # http://stackoverflow.com/questions/528281/how-can-i-include-an-yaml-file-inside-another
    # http://stackoverflow.com/questions/5121931/in-python-how-can-you-load-yaml-mappings-as-ordereddicts
    class Loader(yaml.Loader):
        def __init__(self, stream):
            self._root = os.path.split(stream.name)[0]
            super(Loader, self).__init__(stream)

        def _include(self, node):
            filename = join(self._root, self.construct_scalar(node))
            with open(filename, 'r') as f:
                return yaml.load(f, Loader)

        def _construct_mapping(self, node):
            self.flatten_mapping(node)
            return OrderedDict(self.construct_pairs(node))

    Loader.add_constructor('!include', Loader._include)
    mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
    Loader.add_constructor(mapping_tag, Loader._construct_mapping)

    return yaml.load(stream, Loader)

def yaml_loads(string):
    return yaml_load(StringIO(string))
'''

def ordered_load(stream, loader_class=yaml.Loader, object_pairs_hook=OrderedDict):
    # pylint: disable=too-many-ancestors
    class OrderedLoader(loader_class):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)

def ordered_dump(data, stream=None, dumper_class=yaml.Dumper, default_flow_style=False, **kwds):
    indent = 4
    line_break = '\n'
    # pylint: disable=too-many-ancestors

    class OrderedDumper(dumper_class):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items())
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    kwds.update({'default_flow_style': default_flow_style, 'indent': indent, 'line_break': line_break})
    # WARN: if stream is provided, return value is None
    return yaml.dump(data, stream, OrderedDumper, **kwds)

def yaml_dumps(data):
    "like json.dumps, returns a YAML string"
    return ordered_dump(data, stream=None)

def yaml_dump(data, stream=None):
    "writes output to given file-like object or StringIO if stream not provided"
    if not stream:
        stream = StringIO()
    ordered_dump(data, stream)
    return stream

def remove_ordereddict(data, dangerous=True):
    """turns a nested OrderedDict dict into a regular dictionary.
    dangerous=True will replace unserializable values with the string '[unserializable]' """
    # so nasty.
    return json.loads(json_dumps(data, dangerous))

def listfiles(path, ext_list=None):
    "returns a list of absolute paths for given dir"
    path_list = map(lambda fname: os.path.abspath(join(path, fname)), os.listdir(path))
    if ext_list:
        path_list = filter(lambda path: os.path.splitext(path)[1] in ext_list, path_list)
    return sorted(filter(os.path.isfile, path_list))

def utcnow():
    now = datetime.now()
    return now.replace(tzinfo=pytz.UTC)

def ymd(dt=None, fmt="%Y-%m-%d"):
    "formats a datetime object to YYY-mm-dd format"
    if not dt:
        dt = datetime.now() # TODO: replace this with a utcnow()
    return dt.strftime(fmt)

def ensure(assertion, msg, exception_class=AssertionError):
    """intended as a convenient replacement for `assert` statements that
    get compiled away with -O flags"""
    if not assertion:
        raise exception_class(msg)

def mkdir_p(path):
    os.system("mkdir -p %s" % path)
    ensure(os.path.isdir(path), "directory couldn't be created: %s" % path)
    ensure(os.access(path, os.W_OK | os.X_OK), "directory isn't writable: %s" % path)
    return path

def json_dumps(obj, dangerous=False):
    """drop-in for json.dumps that handles datetime objects.

    dangerous=True will replace unserializable values with the string '[unserializable]'.
    you should typically set this to True. it's False for legacy reasons."""
    def json_handler(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif dangerous:
            return '[unserializable]'
        else:
            raise TypeError('Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj)))
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
# pylint: disable=invalid-name
def lu(context, *paths, **kwargs):
    """looks up many paths given the initial data, returning the first non-nil result.
    if no data available a ValueError is raised."""
    default = None
    if 'default' in kwargs:
        default = kwargs['default']
    v = firstnn(map(lambda path: lookup(context, path, default), paths))
    if v is None:
        raise ValueError("no value available for paths %r. %s" % (paths, context))
    return v

def hasallkeys(ddict, key_list):
    return all(map(ddict.has_key, key_list))

def missingkeys(ddict, key_list):
    "returns all keys in key_list that are not in given ddict"
    return [key for key in key_list if key not in ddict]
