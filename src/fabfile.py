import os

#pylint: disable=unused-wildcard-import,unused-import,wildcard-import

SRC_DIR = os.path.dirname(os.path.abspath(__file__)) # elife-builder/src/

# once called 'THIS_DIR', now deprecated. confusing. use PROJECT_DIR
PROJECT_DIR = os.path.dirname(SRC_DIR)    # elife-builder/

from cfn import *

import aws
import metrics, report
import packer
import website
import tasks
import lax
from deploy import deploy
