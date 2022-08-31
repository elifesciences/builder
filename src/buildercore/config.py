"""Configuration file for `buildercore`.

buildercore was originally part of builder, then separated out
into it's own project 'builder-core' but was eventually re-integrated.
This transition meant that `src/buildercore/` is still neatly separated
from the interface logic in `./src/taskrunner.py`.

"""
import os
import getpass
from os.path import join
from buildercore import utils
from buildercore.utils import lmap, lfilter
from kids.cache import cache
import logging

# *_DIR are relative
# *_PATH are absolute
# *_FILE are absolute paths to a file
# filenames are names of files without any other context

# prevent the spread of calls to 'os.environ' through the code.
ENV = {
    # envvar, default
    'LOG_LEVEL_FILE': 'INFO',
    # note: simple presence of this envvar will switch it to True
    # so 'BUILDER_NON_INTERACTIVE=false ./bldr foo' will see the string 'false' and go `bool('false')` => `True`
    'BUILDER_NON_INTERACTIVE': None, # interactive by default
    'BUILDER_TIMEOUT': 600, # seconds, 10 minutes
    'CUSTOM_SSH_KEY': '~/.ssh/id_rsa',
    'BLDR_TWI_REUSE_STACK': 0, # False
    'BLDR_TWI_CLEANUP': 1, # True
    'BLDR_ROLE': None, # or 'admin', see taskrunner.py
    'PROJECT': None,
    'INSTANCE': None,
    'BLDR_BACKEND': 'threadbare',
    'BUILDER_TOPFILE': '',
}
ENV = {k: os.environ.get(k, default) for k, default in ENV.items()}

ROOT_USER = 'root'
BOOTSTRAP_USER = 'ubuntu'
DEPLOY_USER = 'elife'
CI_USER = 'jenkins'

WHOAMI = getpass.getuser()

STACK_AUTHOR = WHOAMI # added to context data, see cfngen.py

PROJECT_PATH = os.getcwd() # "/path/to/elife-builder/"
SRC_PATH = join(PROJECT_PATH, 'src') # "/path/to/elife-builder/src/"

TEMP_PATH = "/tmp/"

CFN = ".cfn"

MASTER_SERVER_IID = "master-server--prod"

STACK_DIR = join(CFN, "stacks") # "./.cfn/stacks"
CONTEXT_DIR = join(CFN, "contexts") # "./.cfn/stacks"
SCRIPTS_DIR = "scripts"
PRIVATE_DIR = "private"
KEYPAIR_DIR = join(CFN, "keypairs") # "./.cfn/keypairs"
# the .cfn dir was for cloudformation stuff, but we keep keypairs in there too, so this can't hurt
# perhaps a namechange from .cfn to .state or something later
TERRAFORM_DIR = join(CFN, "terraform")

STACK_PATH = join(PROJECT_PATH, STACK_DIR) # "/.../.cfn/stacks/"
CONTEXT_PATH = join(PROJECT_PATH, CONTEXT_DIR) # "/.../.cfn/contexts/"
KEYPAIR_PATH = join(PROJECT_PATH, KEYPAIR_DIR) # "/.../.cfn/keypairs/"
SCRIPTS_PATH = join(PROJECT_PATH, SCRIPTS_DIR) # "/.../scripts/"

# create all necessary paths and ensure they are writable
lmap(utils.mkdir_p, [TEMP_PATH, STACK_PATH, CONTEXT_PATH, SCRIPTS_PATH, KEYPAIR_PATH])

# logging

LOG_DIR = "logs"
LOG_PATH = join(PROJECT_PATH, LOG_DIR) # /.../logs/
LOG_FILE = join(LOG_PATH, "app.log") # /.../logs/app.log
utils.mkdir_p(LOG_PATH)

FORMAT = logging.Formatter("%(asctime)s - %(levelname)s - %(processName)s - %(name)s - %(message)s")
CONSOLE_FORMAT = logging.Formatter("%(levelname)s - %(name)s - %(message)s")

# http://docs.python.org/2/howto/logging-cookbook.html
ROOTLOG = logging.getLogger() # important! this is the *root LOG*
# all other LOGs are derived from this one
ROOTLOG.setLevel(logging.DEBUG) # *default* output level for all LOGs

# StreamHandler sends to stderr by default
CONSOLE_HANDLER = logging.StreamHandler()
CONSOLE_HANDLER.setLevel(logging.INFO) # output level for *this handler*
CONSOLE_HANDLER.setFormatter(CONSOLE_FORMAT)


# FileHandler sends to a named file
FILE_HANDLER = logging.FileHandler(LOG_FILE)
_log_level = ENV['LOG_LEVEL_FILE']
FILE_HANDLER.setLevel(getattr(logging, _log_level))
FILE_HANDLER.setFormatter(FORMAT)

ROOTLOG.addHandler(CONSOLE_HANDLER)
ROOTLOG.addHandler(FILE_HANDLER)

LOG = logging.getLogger(__name__)
logging.getLogger('paramiko.transport').setLevel(logging.ERROR)
# TODO: leave on for FILE_HANDLER but not for CONSOLE_HANDLER
# logging.getLogger('botocore.vendored').setLevel(logging.ERROR)

# disables the endless log messages from boto:
# 2021-11-09 15:43:51,541 botocore.credentials [INFO] Found credentials in shared credentials file: ~/.aws/credentials
# INFO - botocore.credentials - Found credentials in shared credentials file: ~/.aws/credentials
logging.getLogger('botocore.credentials').setLevel(logging.WARNING)

def get_logger(name):
    "ensures logging is setup before handing out a Logger object to use"
    return logging.getLogger(name)

#
# remote
#

# where the builder can write stuff that should persist across installations/users
# like ec2 instance keypairs
BUILDER_BUCKET = 'elife-builder'
BUILDER_REGION = 'us-east-1'
BUILDER_NON_INTERACTIVE = bool(ENV['BUILDER_NON_INTERACTIVE'])
BUILDER_TIMEOUT = int(ENV['BUILDER_TIMEOUT'])

# how often should we contact the AWS API while polling?
# a value <=2 and the likelihood of throttling goes up.
AWS_POLLING_INTERVAL = 4 # seconds

KEYPAIR_PREFIX = 'keypairs/'
CONTEXT_PREFIX = 'contexts/'

# these sections *shouldn't* be merged if they *don't* exist in the project
CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT = ['rds', 'ext', 'elb', 'alb', 'cloudfront', 'elasticache', 'fastly', 'eks', 'docdb', 'waf']

#
# settings
# buildercore.config is NOT the place for user config
#

PROJECTS_FILES = ['projects/elife.yaml']  # , 'src/tests/fixtures/projects/']

CLONED_PROJECT_FORMULA_DIR = os.path.join(PROJECT_PATH, 'cloned-projects') # same path as used by Vagrant

USER_PRIVATE_KEY = ENV['CUSTOM_SSH_KEY']

#
# testing
#

# 'Test With Instance', see integration_tests.test_with_instance
TWI_REUSE_STACK = ENV['BLDR_TWI_REUSE_STACK'] == '1' # use existing test stack if exists
TWI_CLEANUP = ENV['BLDR_TWI_CLEANUP'] == '1' # tear down test stack after testing

#
# logic
#

def _parse_path(project_path):
    "convert a path into a triple of (protocol, hostname, path)"
    bits = project_path.split('://', 1)
    if len(bits) == 2:
        # "http://example.org/path/to/org/file" => (http, example.org, '/path/to/org/file/')
        protocol, rest = bits
        host, path = rest.split('/', 1)
        return (protocol, host, '/' + path)

    # "/path/to/org/somefile" => (file, None, '/path/to/org/somefile')
    # "/path/to/org/somedir" => (dir, None, '/path/to/org/somedir/')
    path = os.path.abspath(os.path.expanduser(project_path))
    protocol = 'file' if os.path.isfile(path) else 'dir'
    host = None
    return (protocol, host, path)

def _expand_dir_path(triple):
    "any yaml files in any given directories will be found and used"
    protocol, host, path = triple
    if protocol in ['dir', 'file'] and not os.path.exists(path):
        LOG.warning("could not resolve %r, skipping", path)
        return [None]
    if protocol == 'dir':
        return lmap(_parse_path, utils.listfiles(path, ['.yaml']))
    return [triple]

def parse_path_list(path_list):
    """convert the list of project configuration paths to a list of (protocol, host, path) triples.
    local paths that point to directories will be expanded to include all project.yaml inside it.
    duplicate paths and paths that do not exist are removed."""

    # convert a list of paths to a list of triples
    path_list = lmap(_parse_path, path_list)

    # we don't want dirs, we want files
    path_list = utils.shallow_flatten(map(_expand_dir_path, path_list))

    # remove any bogus values
    path_list = lfilter(None, path_list)

    # remove any duplicates. can happen when we expand dir => files
    path_list = utils.unique(path_list)

    return path_list

@cache
def app(settings_path=None):
    return {
        'project-locations': parse_path_list([join(PROJECT_PATH, f) for f in PROJECTS_FILES]),
    }
