"handles the creation/deletion/storage of keypairs from AWS"

import logging
import os
import shutil
from os.path import join

from . import config, core, s3, utils
from .command import local
from .core import stack_pem
from .utils import lfilter

LOG = logging.getLogger(__name__)

#
# s3
#

def s3_keypair_key(stackname):
    return config.KEYPAIR_PREFIX + stackname + ".pem"

def write_keypair_to_s3(stackname):
    # this is the path to where .save() puts it
    # http://boto.readthedocs.io/en/latest/ref/ec2.html#boto.ec2.keypair.KeyPair
    path = stack_pem(stackname, die_if_doesnt_exist=True)
    key = s3_keypair_key(stackname)
    with open(path, 'r') as fp:
        pem_contents = fp.read()
    s3.write(key, pem_contents)
    return s3.exists(key)

def delete_keypair_from_s3(stackname):
    key = s3_keypair_key(stackname)
    s3.delete(key)
    return s3.exists(key)

def download_from_s3(stackname, die_if_exists=True):
    expected_path = stack_pem(stackname, die_if_exists=die_if_exists)
    s3.download(s3_keypair_key(stackname), expected_path, overwrite=True)
    stack_pem(stackname, die_if_doesnt_exist=True)
    local('chmod 400 %s' % expected_path)
    return expected_path

#
# fs
#

def delete_keypair_from_fs(stackname):
    "returns True if the expected keypair for the given stackname can't be found on the filesystem"
    expected_key = stack_pem(stackname)
    if not os.path.exists(expected_key):
        LOG.warning("private key %r not deleted: found %r", stackname, expected_key)
        return True
    try:
        delete_path = join(config.KEYPAIR_PATH, "deleted")
        utils.mkdir_p(delete_path)
        shutil.copy2(expected_key, delete_path)
        os.unlink(expected_key)
        return True
    except (RuntimeError, IOError):
        LOG.exception("unhandled exception attempting to delete keypair from filesystem")

#
#
#

def create_keypair(stackname):
    "creates the ec2 keypair and writes it to s3"
    expected_key = stack_pem(stackname, die_if_exists=True)
    ec2 = core.boto_conn(stackname, 'ec2')
    keypair = ec2.create_key_pair(KeyName=stackname)
    with open(expected_key, 'w') as fh:
        fh.write(keypair.key_material)
    os.chmod(expected_key, 0o600)
    write_keypair_to_s3(stackname)
    return expected_key

def delete_keypair(stackname):
    "deletes the keypair from ec2, s3 and locally if it exists"
    ec2 = core.boto_conn(stackname, 'ec2')
    keypair = ec2.KeyPair(stackname)
    keypair.delete() # delete from aws
    delete_keypair_from_s3(stackname) # delete from s3
    delete_keypair_from_fs(stackname) # delete from fs

#
#
#

def all_in_s3():
    return lfilter(None, map(os.path.basename, s3.simple_listing(config.KEYPAIR_PREFIX)))

def all_locally():
    "all keypairs on the filesystem"
    keys = os.listdir(config.KEYPAIR_PATH)
    key_paths = map(lambda fname: join(config.KEYPAIR_PATH, fname), keys)
    return lfilter(os.path.isfile, key_paths)
