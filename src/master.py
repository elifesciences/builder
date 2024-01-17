"""Tasks we perform on the master server.

See `askmaster.py` for tasks that are run on minions."""

import logging
import os

import cfn
import utils
from buildercore import (
    bootstrap,
    config,
    context_handler,
    core,
    keypair,
)
from buildercore.command import local
from buildercore.utils import ensure, lmap
from decorators import echo_output, requires_aws_stack
from kids.cache import cache as cached

LOG = logging.getLogger(__name__)

def update(master_stackname=None):
    "same as `cfn.update` but also removes any orphaned minion keys"
    master_stackname = master_stackname or core.find_master(utils.find_region())
    bootstrap.update_stack(master_stackname, service_list=[
        'ec2' # master-server should be a self-contained EC2 instance
    ])
    bootstrap.remove_all_orphaned_keys(master_stackname)

#
#
#

def write_missing_keypairs_to_s3():
    "uploads any missing ec2 keys to S3 if they're present locally"
    remote_keys = keypair.all_in_s3()
    local_paths = keypair.all_locally()
    local_keys = lmap(os.path.basename, local_paths)

    to_upload = set(local_keys).difference(set(remote_keys))

    print('remote:', remote_keys)
    print('local:', local_keys)
    print('to upload:', to_upload)

    def write(key):
        stackname = os.path.splitext(key)[0]
        keypair.write_keypair_to_s3(stackname)

    lmap(write, to_upload)

@requires_aws_stack
@echo_output
def download_keypair(stackname):
    try:
        return keypair.download_from_s3(stackname)
    except OSError as err:
        LOG.info(err)

#
#
#

@echo_output
@cached
def server_access():
    """Prints True if builder has access to the master server.
    Access may be available because you created the master-server.
    Access may be available via master-server's allowed_keys list."""
    stackname = core.find_master(core.find_region())
    nodes = core.ec2_data(stackname)
    ensure(nodes, "no master-server found!")
    ensure(len(nodes) == 1, "more than one master-server found!")
    public_ip = nodes[0]['PublicIpAddress']
    result = local('ssh -o "StrictHostKeyChecking no" %s@%s "exit"' % (config.BOOTSTRAP_USER, public_ip))
    return result['succeeded']

@requires_aws_stack
def update_salt(stackname):
    "updates the Salt version installed on the instances for the given stack"

    # start instance if it is stopped
    # acquire a lock from Alfred (if possible) so instance isn't shutdown while being updated
    cfn._check_want_to_be_running(stackname, autostart=True)

    context = context_handler.load_context(stackname)

    if not context.get('ec2'):
        LOG.info("no ec2 context. skipping stack: %s", stackname)
        return None

    LOG.info("upgrading stack's salt minion")

    pdata = core.project_data_for_stackname(stackname)
    context['project']['salt'] = pdata['salt']

    LOG.info("updating stack's context")
    context_handler.write_context(stackname, context)

    LOG.info("updating stack's nodes (sequentially)")
    bootstrap.update_ec2_stack(stackname, context, concurrency='serial')
    return True
