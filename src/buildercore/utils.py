from io import StringIO
from ruamel.yaml import YAML
from pprint import pformat
import pytz
import os, sys, json, time, random, string
from functools import wraps
from datetime import datetime
import yaml
from collections import OrderedDict
from os.path import join
import logging
from kids.cache import cache as cached
import tempfile, shutil, copy

LOG = logging.getLogger(__name__)

def ensure(assertion, msg, exception_class=AssertionError):
    """intended as a convenient replacement for `assert` statements that
    get compiled away with -O flags"""
    if not assertion:
        raise exception_class(msg)

def lmap(func, *iterable):
    return list(map(func, *iterable))

def lfilter(func, *iterable):
    return list(filter(func, *iterable))

def keys(d):
    return list(d.keys())

def lzip(*iterable):
    return list(zip(*iterable))

def merge(d1, d2):
    d0 = {}
    d0.update(d1)
    d0.update(d2)
    return d0

def deepcopy(x):
    # return pickle.loads(pickle.dumps(x, -1))
    return copy.deepcopy(x) # very very slow

def isint(v):
    return str(v).lstrip('-+').isdigit()

def isstr(v):
    return isinstance(v, str)

def shallow_flatten(lst):
    "flattens a single level of nesting [[1] [2] [3]] => [1 2 3]"
    return [item for sublist in list(lst) for item in sublist]

# lsh@2022-08-31: removed more-itertools in favour of:
# - https://stackoverflow.com/questions/44628186/convert-python-list-to-ordered-unique-values
def unique(lst):
    "returns a new list of items from given `lst` with duplicates removed, preserving item order."
    #from more_itertools import unique_everseen
    # return list(unique_everseen(lst))
    seen = set()
    return [x for x in lst if x not in seen and seen.add(x) is None]

def conj(x, y):
    "performs a non-mutating update of dict a with the contents of dict b"
    z = deepcopy(x)
    z.update(y)
    return z

def dictfilter(func, ddict):
    "return a subset of dictionary items where func(key, val) is True"
    if not func:
        return ddict
    return {k: v for k, v in ddict.items() if func(k, v)}

def dictmap(fn, ddict):
    return {key: fn(key, val) for key, val in list(ddict.items())}

def nested_dictmap(fn, ddict):
    "`fn` should accept both key and value and return a new key and new value. dictionary values will have `fn` applied to them in turn"
    if not fn:
        return ddict
    for key, val in list(ddict.items()):
        new_key, new_val = fn(key, val)
        if isinstance(new_val, dict):
            new_val = nested_dictmap(fn, new_val)
        if key != new_key:
            del ddict[key] # if the key is modified, we don't want it hanging around
        ddict[new_key] = new_val # always replace value
    return ddict

def subdict(ddict, key_list):
    # aka delall rmkeys
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
    return lfilter(func, data), lfilter(complement(func), data)

def mkidx(fn, lst):
    groups = {}
    for v in lst:
        key = fn(v)
        grp = groups.get(key, [])
        grp.append(v)
        groups[key] = grp
    return groups

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
    ensure(isint(n), "n must be an integer", TypeError)
    try:
        return list(x)[n]
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

# pylint: disable=too-many-arguments
def call_while(fn, interval=5, timeout=600, update_msg="waiting ...", done_msg="done.", exception_class=None):
    """calls the given function `fn` every `interval` seconds until it returns False.
    An `exception_class` will be raised if `timeout` is reached (default `RuntimeError`).
    Any exception objects returned from `fn` will be raised."""
    if not exception_class:
        exception_class = RuntimeError
    elapsed = 0
    while True:
        if update_msg:
            LOG.info(update_msg)
        result = fn()
        if not result:
            break
        if elapsed >= timeout:
            # "Reached timeout 120s"
            message = "Reached timeout %ds" % timeout
            if update_msg:
                # "Reached timeout 120s while waiting ..."
                message += " while %s" % update_msg
            if isinstance(result, BaseException):
                # "Reached timeout 120s while waiting ... (some useful error message)"
                message = message + (" (%s)" % result)
            raise exception_class(message)
        time.sleep(interval)
        elapsed = elapsed + interval
    LOG.info(done_msg)

def call_while_example():
    "a simple example of how to use the `call_while` function. polls fs every two seconds until /tmp/foo is detected"
    def file_doesnt_exist():
        return not os.path.exists("/tmp/foo")
    call_while(file_doesnt_exist, interval=2, update_msg="waiting for /tmp/foo to be created", done_msg="/tmp/foo found")

def updatein(data, path, newval, create=False):
    """mutator. updates a value within a nested dict.
    for example: `updatein({"foo": {"bar": "boo"}}, "foo.bar", "baz")` => `{"foo": {"bar": "baz"}}`
    use `create=True` to create the path if it doesn't already exist.
    for example: `updatein({}, "foo.bar", "baz")` => `{"foo": {"bar": "baz"}}`"""

    bit, rest = path, None
    if isinstance(path, str):
        path_bits = path.split('.')
        bit, rest = path_bits[0], path_bits[1:]

    if not rest:
        # we've come to the end of the path
        data[bit] = newval
        return data

    if create and bit not in data:
        data[bit] = {}

    data[bit] = updatein(data[bit], ".".join(rest), newval, create)

    return data

def random_alphanumeric(length=32):
    rand = random.SystemRandom()
    return ''.join(rand.choice(string.ascii_letters + string.digits) for _ in range(length))

def yaml_load(stream, loader_class=yaml.Loader, object_pairs_hook=OrderedDict):
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
    "wrapper around the yaml.dump function with sensible defaults for formatting"
    indent = 4
    line_break = '\n'
    # pylint: disable=too-many-ancestors

    if isinstance(data, bytes):
        # simple bytestrings are treated as regular (utf-8) strings and not binary data in python3+
        # this doesn't apply to bytestrings used as keys or values in a list
        data = data.decode()

    class OrderedDumper(dumper_class):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            list(data.items()))
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    kwds.update({'default_flow_style': default_flow_style, 'indent': indent, 'line_break': line_break})
    # WARN: if stream is provided, return value is None
    return yaml.dump(data, stream, OrderedDumper, **kwds)

def yaml_dumps(data):
    "returns a YAML string like `json.dumps`. alias for `ordered_dump`."
    return ordered_dump(data)

def yaml_dump(data, stream):
    "like json.dump, writes output to given file-like object. returns None."
    ordered_dump(data, stream)

def remove_ordereddict(data, dangerous=True):
    """turns a nested OrderedDict dict into a regular dictionary.
    dangerous=True will replace unserializable values with the string '[unserializable]' """
    # so nasty.
    return json.loads(json_dumps(data, dangerous))

def listfiles(path, ext_list=None):
    """returns a list of absolute paths for given `path`.
    any file extensions in `ext_list` will filter the list of files returned."""
    path_list = [os.path.abspath(join(path, fname)) for fname in os.listdir(path)]
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

def mkdir_p(path):
    os.system("mkdir -p %s" % path)
    ensure(os.path.isdir(path), "directory couldn't be created: %s" % path)
    ensure(os.access(path, os.W_OK | os.X_OK), "directory isn't writable: %s" % path)
    return path

def json_dumps(obj, dangerous=False, **kwargs):
    """drop-in for json.dumps that handles datetime objects.
    dangerous=True will replace unserializable values with the string '[unserializable]'."""
    def json_handler(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if dangerous:
            return '[unserializable: %s]' % (str(obj))
        raise TypeError('Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj)))
    return json.dumps(obj, default=json_handler, **kwargs)

def lookup(data, path, default=0xDEADBEEF):
    """recursively navigates the `data` dict using the given dot-delimited `path`,
    raising a `KeyError` if a value is not present or `default`."""
    if not isinstance(data, dict):
        raise ValueError("lookup context must be a dictionary")
    if not isstr(path):
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

# TODO: this function suffers from truthy-falsey problems. prefer `lookup`.
# pylint: disable=invalid-name
def lu(context, *paths, **kwargs):
    """looks up many paths given the initial data, returning the first non-nil result.
    if no data available a ValueError is raised."""
    default = None
    if 'default' in kwargs:
        default = kwargs['default']
    v = firstnn(map(lambda path: lookup(context, path, default), paths))
    if v is None:
        raise ValueError("no value available for paths %r. %s" % (paths, pformat(context)))
    return v

def hasallkeys(ddict, key_list):
    "predicate, returns true if all keys in given key_list are present in dictionary ddict"
    return all([key in ddict for key in key_list])

def missingkeys(ddict, key_list):
    "returns all keys in key_list that are not in given ddict"
    return [key for key in key_list if key not in ddict]

def renkey(ddict, oldkey, newkey):
    "mutator. renames a key in-place in given ddict from oldkey to newkey"
    if oldkey in ddict:
        ddict[newkey] = ddict[oldkey]
        del ddict[oldkey]
    return ddict

def renkeys(ddict, pair_list):
    "mutator"
    for oldkey, newkey in pair_list:
        renkey(ddict, oldkey, newkey)

def delkey(d, k):
    "mutator. deletes the key `k` from the dict `d` if `k` in `d`"
    if k in d:
        del d[k]

def tempdir():
    # usage: tempdir, killer = tempdir(); killer()
    name = tempfile.mkdtemp()
    return (name, lambda: shutil.rmtree(name))

@cached
def http_responses():
    """a map of integers to response reason phrases

    e.g. 404: 'Not Found'"""
    import http.client
    return http.client.responses

def visit(d, f, p=None):
    """visits each value in `d` and applies function `f` to it.
    if predicate `p` is given and `p(d)` is false-y, do not visit `d`."""
    if p is None:
        def p(_):
            return True
    if isinstance(d, dict) and p(d):
        return {k: visit(v, f, p) for k, v in d.items()}
    if isinstance(d, list) and p(d):
        return [visit(v, f, p) for v in d]
    if p(d):
        return f(d)
    return d

# ---

def ruamel_load(stream):
    "reads YAML data from given `stream` using the ruamel library."
    yml = YAML(typ='rt') # 'rt' ('round trip') ??
    return yml.load(stream)

def _top_level_separators(s):
    """a YAML string pre-processor applied prior to being written to file by ruamel.
    it adds a newline between top-level entries."""
    retval = ''
    open = None
    for line in s.splitlines():
        if line and line[0] == ' ':
            open = True
        else:
            if open is True and line:
                retval += '\n'
            open = False
        retval += line
        retval += '\n'
    return retval

def ruamel_dump(data, stream):
    "writes a YAML representation of the given `data` to the given `stream` using the ruamel library."
    yml = YAML()
    yml.default_flow_style = False
    yml.indent = 4
    yml.width = 4096
    return yml.dump(data, stream, transform=_top_level_separators)

def ruamel_dumps(data):
    "returns a YAML representation of the given `data` using the ruamel library."
    # bit of a rant:
    # - https://yaml.readthedocs.io/en/latest/example.html#output-of-dump-as-a-string
    stream = StringIO()
    ruamel_dump(data, stream)
    return stream.getvalue()
