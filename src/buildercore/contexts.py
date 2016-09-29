"handles the storage of context from AWS"

import json
from os.path import join, exists
from . import config, s3
from .decorators import if_enabled

import logging
LOG = logging.getLogger(__name__)

def s3_context_key(stackname):
    return config.CONTEXT_PREFIX + stackname + ".json"

def local_context_file(stackname):
    return join(config.CONTEXT_DIR, stackname + ".json")

def load_context(stackname):
    path = local_context_file(stackname)
    if not exists(path):
        download_from_s3(stackname)
    with open(path, 'r') as context_file:
        return json.loads(context_file.read())

def write_context(stackname, contents):
    write_context_locally(stackname, contents)
    write_context_to_s3(stackname)

def write_context_locally(stackname, contents):
    open(local_context_file(stackname), 'w').write(contents)

@if_enabled('write-contexts-to-s3', silent=True)
def write_context_to_s3(stackname):
    path = local_context_file(stackname)
    key = s3_context_key(stackname)
    s3.write(key, open(path, 'r'), overwrite=True)

@if_enabled('write-contexts-to-s3', silent=True)
def delete_context_from_s3(stackname):
    key = s3_context_key(stackname)
    return s3.delete(key)
    
@if_enabled('write-contexts-to-s3', silent=True)
def download_from_s3(stackname):
    expected_path = local_context_file(stackname)
    s3.download(s3_context_key(stackname), expected_path)
    return expected_path
