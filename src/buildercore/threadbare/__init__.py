import os

if os.path.exists("README.md"):
    data = open("README.md").read()
    __doc__ = str(data)

# gevent is used by parallel-ssh which interferes with Python multiprocessing and futures
# it can cause indefinite blocking.
# this bit of magic appears to make everything work nicely with each other.
# - http://www.gevent.org/api/gevent.monkey.html
from gevent import monkey

monkey.patch_all()


from . import state, operations, execute

assert state and operations and execute  # quieten pyflakes

import logging

disable_these_handlers = ["pssh.host_logger", "pssh.clients.native.single"]
for unwanted_logger in disable_these_handlers:
    logger = logging.getLogger(unwanted_logger)
    logger.setLevel(logging.CRITICAL)
