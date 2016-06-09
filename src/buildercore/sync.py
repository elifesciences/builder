#!/usr/bin/env python

__author__ = ['Luke Skibinski <l.skibinski@elifesciences.org>']
__copyright__ = 'eLife Sciences, 2016'
__licence__ = None # private repo
__description__ = "Handles synchronisation of project data with remote s3 bucket"

import os
from buildercore import config, utils
from functools import wraps, partial
from .decorators import osissue, osissuefn
import logging

LOG = logging.getLogger(__name__)

@osissue("refactor. deploy-user.pem ties this to the shared-everything strategy")
def init():
    utils.mkdir_p(config.SYNC_DIR)

def require_syncing(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not config.SYNC_ENABLED:
            LOG.info("syncing has been disabled")
            return
        return fn(*args, **kwargs)
    return wrapper

@require_syncing
def sync_down(destructive=False, sync_dir=config.SYNC_DIR):
    """copies files in remote dir down to local dir
    that have changed or don't exist. if destructive, files
    that don't exist remotely that DO exist locally will be deleted."""
    print "syncing '%s' from S3 %s ..." % (sync_dir, 'DESTRUCTIVELY' if destructive else '')
    # --exact-timestamps
    # if syncing from s3 to local, and both local and remote have the
    # same filesize, s3 won't sync unless you tell it to look at the timestamps.
    cmd = "aws s3 sync s3://%s/%s/ %s --exact-timestamps" % (config.SYNC_BUCKET, sync_dir, sync_dir)
    if destructive:
        cmd += " --delete"
    retval = os.system(cmd)
    init()
    return retval

@require_syncing
def sync_up(destructive=False, sync_dir=config.SYNC_DIR):
    """copies files in local dir up to remote dir that have
    changed or don't exist. if destructive, files that don't
    exist locally that DO exist remotely will be deleted."""
    init()
    print "syncing '%s' to S3 %s ..." % (sync_dir, 'DESTRUCTIVELY' if destructive else '')
    cmd = "aws s3 sync %s s3://elife-builder/%s/" % (sync_dir, sync_dir)
    if destructive:
        cmd += " --delete"
    return os.system(cmd)

#
#
#

#pylint: disable=global-variable-not-assigned
_SYNCED = {}

@require_syncing
def do_sync(acallable=None, sync_dir=config.SYNC_DIR):
    """does a sync down and then a destructive sync up, 
    calling `acallable` in between if given and returning it's 
    results. 

    does *not* sync if already within a callable being sync'ed 
    
    avoid using this with a long-running callable! 
    think of database transaction that are not atomic!
    downloads files (fine) calls callable (...) uploads DESTRUCTIVELY.
    if during the time the callable is being called, other changes happen 
    remotely, those changes will be destroyed.
    """
    resp = -1
    retval = None
    try:
        global _SYNCED
        # am I already syncing?
        if not _SYNCED.get(sync_dir, False):
            # no? then copy down everything the server has
            resp = sync_down(destructive=False, sync_dir=sync_dir)
            # tell anything else down the chain that we're syncing
            # prevents multiple syncs during single task
            _SYNCED[sync_dir] = True
        if acallable:
            retval = acallable()
    except:
        raise
    finally:
        # ... then sync any changes you've made back to s3, including the deletion of files
        if resp == 0:
            # but only do this if the sync down was successful
            sync_up(destructive=True, sync_dir=sync_dir)
    return retval

#
# decorators
#

def _sync_dir(sync_dir=config.SYNC_DIR):
    def wrap1(func):
        @wraps(func)
        def wrap2(*args, **kwargs):
            # if syncing disabled, call wrapped function and return results
            if not config.SYNC_ENABLED:
                return func(*args, **kwargs)
            # ... otherwise, soft sync down, call func, hard sync up, return func results
            return do_sync(partial(func, *args, **kwargs), sync_dir)
        return wrap2
    return wrap1

#pylint: disable=invalid-name
sync_stack = _sync_dir()

def sync_stacks_down(func):
    "ensure we have all stacks available to us before calling this func. DOES NOT COPY BACK UP"
    @wraps(func)
    def wrapper(*args, **kwargs):
        sync_down()
        return func(*args, **kwargs)
    return wrapper
