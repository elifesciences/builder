import copy
import contextlib

CLEANUP_KEY = "_cleanup"


class LockableDict(dict):
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
        # print("self:",self.__dict__, "data:",self)
        if hasattr(self, "read_only") and self.read_only:
            raise ValueError(
                "dictionary is locked attempting to `set` %r with %r" % (key, val)
            )
        dict.__setitem__(self, key, val)


def read_only(d):
    if hasattr(d, "read_only"):
        d.read_only = True


def read_write(d):
    if hasattr(d, "read_only"):
        d.read_only = False


def init_state():
    new_env = LockableDict()
    read_only(new_env)
    return new_env


ENV = init_state()

# used to determine how deeply nested we are
DEPTH = 0


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
def settings(state=None, **kwargs):
    global DEPTH

    if state is None:
        state = ENV
    if not isinstance(state, dict):
        raise TypeError(
            "state map must be a dictionary-like object, not %r" % type(state)
        )

    # deepcopy will attempt to pickle and unpickle all objects in state
    # we can't guarantee what will live in state and if it's possible to pickle it or not
    # the SSHClient is one such unserialisable object that has had to be subclassed
    # another approach would be to relax guarantees that the environment is completely reverted

    original_values = copy.deepcopy(state)
    DEPTH += 1

    read_write(state)
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

        # we're leaving the top-most context decorator
        # ensure state dictionary is marked as read-only
        if DEPTH == 0:
            read_only(state)
