"""app configuration.

Avoid modifying these values during normal usage.

See `settings.yaml.dist` for per-user configuration.

See `config.ENV` for a list of supported envvars and their defaults.

Values in `config.ENV` should override matching values found in `settings.yaml`.

For testing, see `switch_in_test_settings` and `set_config` in `./src/tests/base.py`.

"""
import getpass
import logging
import os
from os.path import join

from buildercore import utils
from buildercore.utils import ensure, lmap

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
    'BLDR_TWI_CLEANUP': '1', # True
    'BLDR_ROLE': None, # or 'admin', see taskrunner.py
    'PROJECT': None,
    'INSTANCE': None,
    'BUILDER_TOPFILE': '',
}
ENV = {k: os.environ.get(k, default) for k, default in ENV.items()}

ROOT_USER = 'root'
BOOTSTRAP_USER = 'ubuntu'
DEPLOY_USER = 'elife'
CI_USER = 'jenkins'

WHOAMI = getpass.getuser()

STACK_AUTHOR = WHOAMI # added to context data, see cfngen.py

PROJECT_PATH = os.getcwd() # "/path/to/builder/"
SRC_PATH = join(PROJECT_PATH, 'src') # "/path/to/builder/src/"

TEMP_PATH = "/tmp/"

CFN_DIR = ".cfn"

MASTER_SERVER_IID = "master-server--prod"

PROJECTS_DIR = "projects"
STACK_DIR = join(CFN_DIR, "stacks") # "./.cfn/stacks"
CONTEXT_DIR = join(CFN_DIR, "contexts") # "./.cfn/stacks"
SCRIPTS_DIR = "scripts"
PRIVATE_DIR = "private"
KEYPAIR_DIR = join(CFN_DIR, "keypairs") # "./.cfn/keypairs"

# lsh@2023-03-29: projects can now specify specfic versions of Terraform to use.
# this is possible using 'tfenv': https://github.com/tfutils/tfenv
TERRAFORM_BIN_PATH = join(PROJECT_PATH, ".tfenv", "bin", "terraform")
# the .cfn dir was for cloudformation stuff, but we keep keypairs in there too, so this can't hurt
# perhaps a namechange from .cfn to .state or something later
TERRAFORM_DIR = join(CFN_DIR, "terraform")

STACK_PATH = join(PROJECT_PATH, STACK_DIR) # "/.../.cfn/stacks/"
CONTEXT_PATH = join(PROJECT_PATH, CONTEXT_DIR) # "/.../.cfn/contexts/"
KEYPAIR_PATH = join(PROJECT_PATH, KEYPAIR_DIR) # "/.../.cfn/keypairs/"
SCRIPTS_PATH = join(PROJECT_PATH, SCRIPTS_DIR) # "/.../scripts/"

# create all necessary paths and ensure they are writable
lmap(utils.mkdir_p, [TEMP_PATH, STACK_PATH, CONTEXT_PATH, SCRIPTS_PATH, KEYPAIR_PATH])

# read user config

USER_SETTINGS_FILE = "settings.yaml"
USER_SETTINGS_PATH = join(PROJECT_PATH, USER_SETTINGS_FILE)
USER = {
    'project-files': [join(PROJECTS_DIR, 'elife.yaml')],
    'stack-files': [],
}
if os.path.exists(USER_SETTINGS_PATH):
    with open(USER_SETTINGS_PATH, 'r') as fh:
        USER.update(utils.yaml_load(fh.read()))

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
CLOUD_EXCLUDING_DEFAULTS_IF_NOT_PRESENT = [
    'rds', 'ext', 'elb', 'alb', 'cloudfront', 'elasticache', 'fastly', 'eks', 'docdb', 'waf'
]

ensure(isinstance(USER['project-files'], list),
       "'project-files' must be a list, not a %r. check your settings.yaml file." % type(USER['project-files']))
# all project files are rooted in the builder project directory. no good reason, subject to change.
PROJECTS_PATH_LIST = [join(PROJECT_PATH, project_file) for project_file in USER['project-files']]

CLONED_PROJECT_FORMULA_PATH = os.path.join(PROJECT_PATH, 'cloned-projects') # same path as used by Vagrant

USER_PRIVATE_KEY = ENV['CUSTOM_SSH_KEY']

#
# testing
#

# TODO: revisit this
# 'Test With Instance', see integration_tests.test_with_instance
TWI_REUSE_STACK = ENV['BLDR_TWI_REUSE_STACK'] == '1' # use existing test stack if exists
TWI_CLEANUP = ENV['BLDR_TWI_CLEANUP'] == '1' # tear down test stack after testing


# ---

STACKS_PATH_LIST = [join(PROJECT_PATH, stack_file) for stack_file in USER['stack-files']]
