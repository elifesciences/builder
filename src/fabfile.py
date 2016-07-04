import os

#pylint: disable=unused-wildcard-import,unused-import,wildcard-import

SRC_DIR = os.path.dirname(os.path.abspath(__file__)) # elife-builder/src/

# once called 'THIS_DIR', now deprecated as confusing.
PROJECT_DIR = os.path.dirname(SRC_DIR)    # elife-builder/

from cfn import *

import aws
import metrics
import packer
import tasks
import lax
import master
import askmaster
import buildvars
from deploy import deploy
