"""Configuration file for `buildercore`.

`buildercore.config` is a place to record assumptions really. 
Settings that the users are encouraged to tweak should go into the 
`settings.yml` file at the root of the project and incorporated here.

buildercore was originally part of the builder, then separated out 
into it's own project 'builder-core' but has now been re-integrated. 
This transition meant that `src/buildercore/` is still neatly separated
from the interface logic in the fabfile.

"""
import os
from os.path import join

from buildercore import utils
from buildercore.utils import first, last, listfiles

import logging


# dirs are relative
# paths are absolute
# a file is an absolute path to a file
# filenames are names of files without any other context


# these users should probably be specified in the project/org config file
# as 'defaults'. deploy user especially
ROOT_USER = 'root'
BOOTSTRAP_USER = 'ubuntu'
DEPLOY_USER = 'elife'

PROJECT_PATH = os.getcwdu() # ll: /path/to/elife-builder/
SRC_PATH = join(PROJECT_PATH, 'src') # ll: /path/to/elife-builder/src/

TEMP_PATH = "/tmp/"

CFN = ".cfn"

STACK_DIR = join(CFN, "stacks") # ll: ./.cfn/stacks
SCRIPTS_DIR = "scripts"
PRIVATE_DIR = "private"
KEYPAIR_DIR = join(CFN, "keypairs") # ll: ./.cfn/keypairs

STACK_PATH = join(PROJECT_PATH, STACK_DIR) # ll: /.../cfn/stacks/
KEYPAIR_PATH = join(PROJECT_PATH, KEYPAIR_DIR) # ll: /.../cfn/keypairs/
SCRIPTS_PATH = join(PROJECT_PATH, SCRIPTS_DIR) # ll: /.../scripts/

# create all necessary paths and ensure they are writable
map(utils.mkdir_p, [TEMP_PATH, STACK_PATH, SCRIPTS_PATH, KEYPAIR_PATH])

## logging

LOG_DIR = "logs"
LOG_PATH = join(PROJECT_PATH, LOG_DIR) # /.../logs/
LOG_FILE = join(LOG_PATH, "app.log") # /.../logs/app.log
utils.mkdir_p(LOG_PATH)

FORMAT = logging.Formatter("%(created)f - %(levelname)s - %(processName)s - %(name)s - %(message)s")

# http://docs.python.org/2/howto/logging-cookbook.html
ROOTLOG = logging.getLogger() # important! this is the *root LOG*
                            # all other LOGs are derived from this one
ROOTLOG.setLevel(logging.DEBUG) # *default* output level for all LOGs

# StreamHandler sends to stderr by default
H1 = logging.StreamHandler()
H1.setLevel(logging.INFO) # output level for *this handler*
H1.setFormatter(FORMAT)

# FileHandler sends to a named file
H2 = logging.FileHandler(LOG_FILE)
H2.setLevel(logging.WARN) # change to INFO if code is less-than-stable
H2.setFormatter(FORMAT)

# root logger sends *everything* to file
ROOTLOG.addHandler(H1)
ROOTLOG.addHandler(H2) 

LOG = logging.getLogger(__name__)

#
# remote 
#

PACKER_BOX_PREFIX = "elifesciences" # the 'elifesciences' in 'elifesciences/basebox'
PACKER_BOX_BUCKET = "elife-builder"
PACKER_BOX_KEY = "boxes"
# ll: s3://elife-builder/boxes
PACKER_BOX_S3_PATH = "s3://%s" % join(PACKER_BOX_BUCKET, PACKER_BOX_KEY)
PACKER_BOX_S3_HTTP_PATH = join("https://s3.amazonaws.com", PACKER_BOX_BUCKET, PACKER_BOX_KEY)

#
# settings
# believe it or not but buildercore.config is NOT the place to be putting settings
#

SETTINGS_FILE = join(PROJECT_PATH, 'settings.yml')


#
# logic
#

def load(settings_yaml_file):
    "read the settings.yml file in from yaml"
    return utils.ordered_load(open(settings_yaml_file, 'r'))

def _parse_loc(loc):
    "turn a project-location path into a triple of (protocol, hostname, path)"
    bits = loc.split('://', 1)
    if len(bits) == 2:
        host, path = bits[1].split('/', 1)
        # ll: (http, example.org, '/path/to/org/file/')
        return (bits[0], host, '/' + path)
    # ll: (file, None, '/path/to/org/file/')
    path = os.path.abspath(os.path.expanduser(loc))
    return 'file' if os.path.isfile(path) else 'dir', None, path

def parse_loc_list(loc_list):
    "wrangle the list of paths the user gave us. expand if they specify a directory, etc"
    # give the convenient user form some structure
    p_loc_list = map(_parse_loc, loc_list)
    # do some post processing
    def expand_dirs(triple):
        protocol, host, path = triple
        if protocol in ['dir', 'file'] and not os.path.exists(path):
            LOG.warn("could not resolve %r, skipping" % path)
            return None
        if protocol == 'dir':
            yaml_files = utils.listfiles(path, ['.yaml'])
            return [('file', host, path) for path in yaml_files]
        return [triple]    
    # we don't want dirs, we want files
    p_loc_list = utils.flatten(map(expand_dirs, p_loc_list))

    # remove any bogus values
    p_loc_list = filter(None, p_loc_list)
    
    # remove any duplicates. can happen when we expand dir => files
    p_loc_list = utils.unique(p_loc_list)

    return p_loc_list

def parse(settings_data):
    "iterate through the settings file and do any data coercion necessary"
    processors = {
        'project-locations': parse_loc_list,
    }
    for key, processor in processors.items():
        settings_data[key] = processor(settings_data[key])
    return settings_data

def app(settings_path=SETTINGS_FILE):
    return parse(load(settings_path))
