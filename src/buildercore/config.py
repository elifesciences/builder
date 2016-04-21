"""Configuration file for builder-core.

builder-core was originally part of the builder, then separated out 
into it's own module 'builder-core' and has now been re-integrated. 
this transition means that src/builder-core/ is still self contained
from the interface logic in the fabfile."""

from buildercore.utils import first, last
import logging
import os
from os.path import join

PROJECT_PATH = os.getcwdu() # ll: /path/to/elife-builder/
SRC_PATH = join(PROJECT_PATH, 'src') # ll: /path/to/elife-builder/src/

PILLAR_DIR = "salt/pillar"

SEP = "-"

# dirs are relative
SYNC_DIR = "cfn"
STACK_DIR = join(SYNC_DIR, "stacks") # ll: cfn/stacks
SCRIPTS_DIR = "scripts"
PRIVATE_DIR = "private"

# paths are absolute
STACK_PATH = join(PROJECT_PATH, STACK_DIR) # ll: /.../cfn/stacks/
SCRIPTS_PATH = join(PROJECT_PATH, SCRIPTS_DIR) # /.../scripts/

ROOT_USER = 'root'
BOOTSTRAP_USER = 'ubuntu'
DEPLOY_USER = 'elife'

## logging

LOG_DIR = "logs"
LOG_PATH = join(PROJECT_PATH, LOG_DIR) # /.../logs/
LOG_FILE = join(LOG_PATH, "app.log") # /.../logs/app.log

FORMAT = logging.Formatter("%(created)f - %(levelname)s - %(processName)s - %(name)s - %(message)s")

os.system("mkdir -p %s" % LOG_PATH)
assert os.path.isdir(LOG_PATH), "log directory couldn't be created: %s" % LOG_PATH
assert os.access(LOG_PATH, os.W_OK | os.X_OK), "log directory isn't writable: %s" % LOG_PATH

# http://docs.python.org/2/howto/logging-cookbook.html
LOG = logging.getLogger("") # important! this is the *root LOG*
                            # all other LOGs are derived from this one
LOG.setLevel(logging.DEBUG) # *default* output level for all LOGs

# StreamHandler sends to stderr by default
H1 = logging.StreamHandler()
H1.setLevel(logging.INFO) # output level for *this handler*
H1.setFormatter(FORMAT)

# FileHandler sends to a named file
H2 = logging.FileHandler(LOG_FILE)
H2.setLevel(logging.WARN) # change to INFO if code is less-than-stable
H2.setFormatter(FORMAT)

LOG.addHandler(H1)
LOG.addHandler(H2)

#
#
#

PROJECTS_DIR = "projects"
PROJECT_FILE_LIST = [
    join(PROJECTS_DIR, "elife.yaml"),
    #join(SYNC_DIR, "elife.yaml"), # projects are in version control within elife-builder
]
# use the first project file that exists or default to the last one defined
PROJECT_FILE = first(filter(os.path.exists, PROJECT_FILE_LIST)) or last(PROJECT_FILE_LIST)
if not PROJECT_FILE:
    LOG.warn("cannot find a project file! I looked here:\n* %s", "\n* ".join(PROJECT_FILE_LIST))
