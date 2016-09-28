"handles the storage of context from AWS"

import os, shutil
from os.path import join
from . import core, utils, config, s3
from .core import stack_pem
from .decorators import if_enabled

import logging
LOG = logging.getLogger(__name__)

def s3_context_key(stackname):
    return config.CONTEXT_PREFIX + stackname + ".json"

def local_context_file(stackname):
    return config.CONTEXT_PATH + "/" + stackname + ".json"

def write_context_to_s3(stackname):
    path = local_context_file(stackname)
    key = s3_context_key(stackname)
    s3.write(key, open(path, 'r'))

def delete_context_from_s3(stackname):
    key = s3_context_key(stackname)
    s3.delete(key)
    
def download_from_s3(stackname):
    expected_path = local_context_file(stackname)
    s3.download(s3_context_key(stackname), expected_path)
    return expected_path
