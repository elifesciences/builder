import copy
import contextlib

CLEANUP_KEY = "_cleanup"


class FreezeableDict(dict):
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.read_only = False

    def update(self, new_dict):
        if self.read_only:
            raise ValueError(
                "dictionary is locked attempting to `update` with %r" % new_dict
            )
        dict.update(self, new_dict)

    def __setitem__(self, key, val):
        # I suspect multiprocessing isn't copying the custom 'read_only' attribute back
        # from the child process results. be aware of this weirdness
        # print("self:", self.__dict__, "internal data:", self)
        if hasattr(self, "read_only") and self.read_only:
            raise ValueError(
                "dictionary is locked attempting to `__setitem__` %r with %r"
                % (key, val)
            )
        dict.__setitem__(self, key, val)


def read_only(d):
    if hasattr(d, "read_only"):
        d.read_only = True


def read_write(d):
    if hasattr(d, "read_only"):
        d.read_only = False


def initial_state():
    """returns a new, empty, locked, FreezeableDict instance that is used as the initial `state.ENV` value.

    if you are thinking "it would be really convenient if 'some_setting' was 'some_value' by default",
    see `set_defaults`."""
    new_env = FreezeableDict()
    read_only(new_env)
    return new_env


ENV = initial_state()

DEPTH = 0  # used to determine how deeply nested we are


def set_defaults(defaults_dict=None):
    """re-initialises the `state.ENV` dictionary with the given defaults.
    With no arguments the global state will be reverted to it's initial state (an empty FreezeableDict).

    Use `state.set_defaults` BEFORE using ANY other `state.*` functions are called."""
    global ENV, DEPTH
    if DEPTH != 0:
        msg = "refusing to set initial `threadbare.state.ENV` state within a `threadbare.state.settings` context manager."
        raise EnvironmentError(msg)

    new_env = FreezeableDict()
    new_env.update(defaults_dict or {})
    read_only(new_env)
    ENV = new_env


def cleanup(old_state):
    if CLEANUP_KEY in old_state:
        for cleanup_fn in old_state[CLEANUP_KEY]:
            cleanup_fn()
        del old_state[CLEANUP_KEY]


def _add_cleanup(state, fn):
    cleanup_fn_list = state.get(CLEANUP_KEY, [])
    cleanup_fn_list.append(fn)
    state[CLEANUP_KEY] = cleanup_fn_list


def add_cleanup(fn):
    "add a function to a list of functions that are called after leaving the current scope of the context manager"
    return _add_cleanup(ENV, fn)


@contextlib.contextmanager
def settings(**kwargs):
    global DEPTH

    state = ENV
    if not isinstance(state, dict):
        raise TypeError(
            "state map must be a dictionary-like object, not %r" % type(state)
        )

    # deepcopy will attempt to pickle and unpickle all objects in state
    # we can't guarantee what will live in state and if it's possible to pickle it or not
    # the SSHClient is one such unserialisable object that has had to be subclassed
    # another approach would be to relax guarantees that the environment is completely reverted

    # call `read_write` here as `deepcopy` copies across attributes (like `read_only`) and
    # then values using `__setitem__`, causing errors in FreezeableDict when 'set_defaults' used
    read_write(state)

    original_values = copy.deepcopy(state)
    DEPTH += 1

    state.update(kwargs)

    # ensure child context processors don't clean up their parents
    if CLEANUP_KEY in state:
        state.update({CLEANUP_KEY: []})

    try:
        yield state
    finally:
        cleanup(state)
        state.clear()
        state.update(original_values)

        DEPTH -= 1

        if DEPTH == 0:
            # we're leaving the top-most context decorator
            # ensure state dictionary is marked as read-only
            read_only(state)
