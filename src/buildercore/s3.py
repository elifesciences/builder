import boto
from boto.s3.connection import Location
from boto.s3.key import Key
from . import core, config
from kids.cache import cache as cached

import logging

LOG = logging.getLogger(__name__)

def connect_s3():
    # we'll need to deal with this assumption
    return core.connect_aws('s3', 'us-east-1') #Location.USWest2)    

@cached
def builder_bucket():
    try:
        nom = config.BUILDER_BUCKET
        return connect_s3().get_bucket(nom)
    except boto.exception.S3ResponseError as err:
        LOG.error("got an S3 error attempting to get the builder bucket. have you created it yet?", \
                      extra={'bucket': nom, 'error': err.message})
        raise

def exists(key):
    return builder_bucket().get_key(key) != None

def write(key, something):
    "stream is a file-like object"
    if exists(key):
        raise KeyError("key %r exists. refusing to overwrite." % key)    
    k = Key(builder_bucket())
    k.key = key
    if isinstance(something, basestring):
        k.set_contents_from_string(something)
    elif isinstance(something, file):
        k.set_contents_from_file(something)
    else:
        raise ValueError("boto can't handle anything much else besides strings and files")

def delete(key):
    "deletes a single key from the builder bucket"
    # legacy prefixes
    protected = ['boxes/', 'cfn/', 'private/']
    if not all(map(lambda prefix: not key.startswith(prefix), protected)):
        msg = "you tried to delete a key with a protected prefix"
        LOG.warn(msg, extra={'key': key, 'protected': protected})
        raise ValueError(msg)
    LOG.info("deleting key", extra={'key': key})
    builder_bucket().get_key(key).delete()
    return not exists(key)
    
def delete_contents(prefix):
    def validate_prefix(prefix):
        prefix = prefix.strip()
        if not prefix or len(prefix) < 2:
            raise ValueError("invalid prefix: %r" % prefix)
        if not prefix.endswith('/'):
            raise ValueError("prefix doesn't start or end in a slash: %r" % prefix)
        if not prefix.startswith('test/'):
            raise ValueError("only prefixes starting with /test/ allowed: %r" % prefix)
    validate_prefix(prefix)
    for key in builder_bucket().list(prefix=prefix):
        LOG.info("deleting key", extra={'key': key})
        key.delete()
