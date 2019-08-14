import os
from botocore.exceptions import ClientError
from . import config, core
from .utils import isstr, ensure
from kids.cache import cache as cached
from io import IOBase
import logging

LOG = logging.getLogger(__name__)

@cached
def builder_bucket():
    "returns connection to the bucket where builder stores templates and credentials."
    try:
        nom, region = config.BUILDER_BUCKET, config.BUILDER_REGION
        resource = core.boto_resource('s3', region)
        bucket = resource.Bucket(nom)
        ensure(bucket in resource.buckets.all(), "bucket %r in region %r does not exist" % (nom, region))
        return bucket
    except ClientError as err:
        LOG.error("unhandled error attempting to find S3 bucket %r in region %r", nom, region,
                  extra={'bucket': nom, 'region': region, 'error': str(err)})
        raise

def exists(key):
    "predicate, returns True if given key in configured bucket+region exists"
    try:
        builder_bucket().Object(key).load()
        return True
    except ClientError as err:
        if err.response['Error']['Code'] == '404':
            return False
        raise

def write(key, something, overwrite=False):
    "stream is a file-like object"
    if exists(key) and not overwrite:
        raise KeyError("key %r exists and overwrite==False. refusing to overwrite." % key)
    k = builder_bucket().Object(key)
    LOG.info("writing key %r", key, extra={'key': key})

    # http://boto3.readthedocs.io/en/latest/reference/services/s3.html#S3.Object.put
    if isstr(something):
        k.put(Body=something.encode()) # bytes
    elif isinstance(something, IOBase):
        # this seek() here is interesting
        # the check in isstr above is actually moving it's pointer
        something.seek(0)
        k.put(Body=something) # py3 file
    # TODO: py2 warning
    elif isinstance(something, file):
        k.put(Body=something) # py2 file
    else:
        raise ValueError("boto can't handle value of type %r, just strings and files" % type(something))

def delete(key):
    "deletes a single key from the builder bucket"
    # legacy prefixes
    protected = ['boxes/', 'cfn/', 'private/']
    if not all([not key.startswith(prefix) for prefix in protected]):
        msg = "you tried to delete a key with a protected prefix"
        LOG.warn(msg, extra={'key': key, 'protected': protected})
        raise ValueError(msg)
    if not exists(key):
        return True
    LOG.info("deleting key %s", key, extra={'key': key})
    k = builder_bucket().Object(key)
    k.delete()
    # http://boto3.readthedocs.io/en/latest/reference/services/s3.html#S3.Object.wait_until_not_exists
    k.wait_until_not_exists()
    return True

def validate_prefix(prefix):
    prefix = prefix.strip()
    if not prefix or len(prefix) < 2:
        raise ValueError("invalid prefix: %r" % prefix)
    if not prefix.endswith('/'):
        raise ValueError("prefix doesn't start or end in a slash: %r" % prefix)
    if not prefix.startswith('test/'):
        raise ValueError("only prefixes starting with /test/ allowed: %r" % prefix)

def delete_contents(prefix):
    validate_prefix(prefix)
    # TODO: optimisation here: http://boto3.readthedocs.io/en/latest/reference/services/s3.html#S3.Bucket.delete_objects
    for key in builder_bucket().objects.filter(Prefix=prefix):
        LOG.info("deleting key %s", key, extra={'key': key})
        key.delete() # not delete(key) ?

def listing(prefix):
    "returns a list of Key objects starting with given prefix rooted in the builder bucket"
    return builder_bucket().objects.filter(Prefix=prefix)

def simple_listing(prefix):
    "returns a realized list of the names of the keys from the `list` function. "
    return [key.key for key in listing(prefix)]

def download(key, output_path, overwrite=False):
    if not overwrite:
        ensure(not os.path.exists(output_path), "given output path exists, will not overwrite: %r" % output_path)
    ensure(exists(key), "key %r not found in bucket %r" % (key, config.BUILDER_BUCKET))
    LOG.info("downloading key %s", key, extra={'key': key})
    builder_bucket().Object(key).download_file(output_path)
    return output_path
