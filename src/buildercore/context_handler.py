# Handles the storage of 'context' with AWS
#
# To build services we first create a simple dictionary of data about
# the service we want to build. This is called the 'context'.
# This data is serialised to JSON and stored locally and on AWS S3.
# A subset of this data is stored on the EC2 instance, if an EC2
# instance exists, and are called `build_vars`.
#
# See cfngen.py for building the context
# See cloudformation.py and trop.py for rendering Cloudformation templates with this context data
# See terraform.py for rendering Terraform templates with this context data

import os, json
from os.path import join
from . import config, s3
from .decorators import if_enabled

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
    if not os.path.exists(path):
        if not download_from_s3(stackname):
            raise MissingContextFile("We are missing the context file for %s, even on S3" % stackname)
    return json.load(open(path, 'r'))

def write_context(stackname, context):
    write_context_locally(stackname, json.dumps(context))
    write_context_to_s3(stackname)

def write_context_locally(stackname, contents):
    open(local_context_file(stackname), 'w').write(contents)

@if_enabled('write-context-to-s3', silent=True)
def write_context_to_s3(stackname):
    path = local_context_file(stackname)
    key = s3_context_key(stackname)
    s3.write(key, open(path, 'rb'), overwrite=True)

@if_enabled('write-context-to-s3', silent=True)
def delete_context_from_s3(stackname):
    key = s3_context_key(stackname)
    return s3.delete(key)

@if_enabled('write-context-to-s3', silent=True)
def download_from_s3(stackname, refresh=False):
    key = s3_context_key(stackname)
    if not s3.exists(key):
        return False

    expected_path = local_context_file(stackname)
    if os.path.exists(expected_path) and refresh:
        os.unlink(expected_path)
    s3.download(key, expected_path)
    return True

def only_if(*servicenames):
    """Decorator that only executes an update function if the context contains a particular servicename that would need it"""
    def decorate_with_only_if(fn):
        def decorated_with_only_if(stackname, context, **kwargs):
            # only update service if stack is using given service
            if [k for k in context.keys() if context.get(k) and k in servicenames]:
                # TODO: context is not always necessary in fn implementations. Can we avoid passing it when not needed?
                return fn(stackname, context, **kwargs)
            LOG.info("Skipped as %s not in the context", servicenames)
        return decorated_with_only_if
    return decorate_with_only_if

class MissingContextFile(RuntimeError):
    pass
