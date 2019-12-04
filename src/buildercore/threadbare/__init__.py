# gevent is used by parallel-ssh which interferes with Python multiprocessing and futures
# it can cause indefinite blocking.
# this bit of magic appears to make everything work nicely with each
# - http://www.gevent.org/api/gevent.monkey.html
from gevent import monkey

monkey.patch_all()
