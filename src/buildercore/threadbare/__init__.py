# gevent is used by parallel-ssh which interferes with Python multiprocessing and futures
# it can cause indefinite blocking.
# The 'NOQA: E402' flags prevent the imports from being re-ordered.
# This bit of magic appears to make everything work nicely with each other:
# - http://www.gevent.org/api/gevent.monkey.html
from gevent import monkey

monkey.patch_all()

import os  # NOQA: E402

if os.path.exists("README.md"):
    data = open("README.md").read()
    __doc__ = str(data)

from . import state, operations, execute  # NOQA: E402

assert state and operations and execute  # quieten pyflakes

import logging  # NOQA: E402

disable_these_handlers = ["pssh.host_logger", "pssh.clients.native.single"]
for unwanted_logger in disable_these_handlers:
    logger = logging.getLogger(unwanted_logger)
    logger.setLevel(logging.CRITICAL)
