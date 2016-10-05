"handles the storage of context from AWS"

import json
from os.path import join, exists
from . import config, s3
from .decorators import if_enabled

# only needed for _fallback_download_context_from_ec2:
from . import core, bvars

import logging
LOG = logging.getLogger(__name__)

def s3_context_key(stackname):
    return config.CONTEXT_PREFIX + stackname + ".json"

def local_context_file(stackname):
    return join(config.CONTEXT_DIR, stackname + ".json")

def load_context(stackname):
    """Returns the store context data structure for 'stackname'.
    
    Downloads from S3 if missing on the local builder instance"""
    path = local_context_file(stackname)
    if not exists(path):
        was_on_s3 = download_from_s3(stackname)
        if not was_on_s3:
            _fallback_download_context_from_ec2(stackname)

    with open(path, 'r') as context_file:
        return json.loads(context_file.read())

def _fallback_download_context_from_ec2(stackname):
    LOG.warn("Context for %s was not on S3, downloading it from EC2 and uploading it", stackname)
    with core.stack_conn(stackname):
        build_vars = bvars.read_from_current_host()
        context = dict(build_vars)
        for key in ['node', 'nodename']:
            if key in context:
                del context[key]
        # these keys must exist, even if None
        for key in ['full_hostname', 'domain', 'int_full_hostname', 'int_domain']:
            assert key in context, "Context is malformed, missing %s key (%s)" % (key, context)
        write_context(stackname, context)

def write_context(stackname, context):
    write_context_locally(stackname, json.dumps(context))
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
    key = s3_context_key(stackname)
    if not s3.exists(key):
        return False

    expected_path = local_context_file(stackname)
    s3.download(key, expected_path)
    return True
