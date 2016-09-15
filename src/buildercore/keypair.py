"handles the creation/deletion/storage of keypairs from AWS"

import os, shutil
from os.path import join
from . import core, utils, config, s3
from .core import stack_pem
from .decorators import if_enabled

import logging
LOG = logging.getLogger(__name__)

#
# s3
#

def s3_keypair_key(stackname):
    return config.KEYPAIR_PREFIX + stackname + ".pem"

@if_enabled('write-keypairs-to-s3', silent=True)
def write_keypair_to_s3(stackname):
    # this is the path to where .save() puts it
    # http://boto.readthedocs.io/en/latest/ref/ec2.html#boto.ec2.keypair.KeyPair
    path = stack_pem(stackname, die_if_doesnt_exist=True)
    key = s3_keypair_key(stackname)
    s3.write(key, open(path, 'r'))
    return s3.exists(key)

@if_enabled('write-keypairs-to-s3', silent=True)
def delete_keypair_from_s3(stackname):
    key = config.KEYPAIR_PREFIX + stackname
    key = s3_keypair_key(stackname)
    s3.delete(key)
    return s3.exists(key)

@if_enabled('write-keypairs-to-s3', silent=True)
def download_from_s3(stackname):
    expected_path = stack_pem(stackname, die_if_exists=True)
    s3.download(s3_keypair_key(stackname), expected_path)
    stack_pem(stackname, die_if_doesnt_exist=True)
    return expected_path

#
# fs
#

def delete_keypair_from_fs(stackname):
    "returns True if the expected keypair for the given stackname can't be found on the filesystem"
    expected_key = stack_pem(stackname)
    if not os.path.exists(expected_key):
        LOG.warn("private key %r not deleted: found %r" % (stackname, expected_key))
        return True
    try:
        delete_path = join(config.KEYPAIR_PATH, "deleted")
        utils.mkdir_p(delete_path)
        shutil.copy2(expected_key, delete_path)
        os.unlink(expected_key)
        return True
    except:
        LOG.exception("unhandled exception attempting to delete keypair from filesystem")

#
# 
#

def create_keypair(stackname):
    "creates the ec2 keypair and writes it to s3"
    expected_key = stack_pem(stackname, die_if_exists=True)
    ec2 = core.connect_aws_with_stack(stackname, 'ec2')
    key = ec2.create_key_pair(stackname)
    # write to fs
    key.save(config.KEYPAIR_PATH) # exclude the filename
    # write to s3
    write_keypair_to_s3(stackname)
    return expected_key

def delete_keypair(stackname):
    "deletes the keypair from ec2, s3 and locally if it exists"
    ec2 = core.connect_aws_with_stack(stackname, 'ec2')
    # delete from aws
    ec2.delete_key_pair(stackname)
    # delete from s3
    delete_keypair_from_s3(stackname)
    # delete from fs
    # TODO: shift this into own func
    # just while debugging, move the deleted key to a 'deleted' dir
    delete_keypair_from_fs(stackname)

#
#
#

@if_enabled('write-keypairs-to-s3')
def all_in_s3():
    return filter(None, map(os.path.basename, s3.simple_listing(config.KEYPAIR_PREFIX)))

def all_locally():
    "all keypairs on the filesystem"
    keys = os.listdir(config.KEYPAIR_PATH)
    key_paths = map(lambda fname: join(config.KEYPAIR_PATH, fname), keys)
    return filter(os.path.isfile, key_paths)
