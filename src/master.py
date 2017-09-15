"""Tasks we perform on the master server.

See `askmaster.py` for tasks that are run on minions."""

import os
import aws
from fabric.api import sudo, task, local
from buildercore import core, bootstrap, config, keypair
from buildercore.utils import last
from decorators import debugtask, echo_output, requires_project, requires_aws_stack, requires_feature
from kids.cache import cache as cached
import logging

LOG = logging.getLogger(__name__)

#
#
#

@debugtask
@requires_feature('write-keypairs-to-s3')
def write_missing_keypairs_to_s3():
    "uploads any missing ec2 keys to S3 if they're present locally"
    remote_keys = keypair.all_in_s3()
    local_paths = keypair.all_locally()
    local_keys = map(os.path.basename, local_paths)

    to_upload = set(local_keys).difference(set(remote_keys))

    print 'remote:', remote_keys
    print 'local:', local_keys
    print 'to upload:', to_upload

    def write(key):
        stackname = os.path.splitext(key)[0]
        keypair.write_keypair_to_s3(stackname)

    map(write, to_upload)

def write_missing_context_to_s3():
    pass

@debugtask
@requires_feature('write-keypairs-to-s3')
@requires_aws_stack
@echo_output
def download_keypair(stackname):
    try:
        path = keypair.download_from_s3(stackname)
        local('chmod 400 -R %s' % path)
        return path
    except EnvironmentError as err:
        LOG.info(err.message)

#
#
#

@debugtask
@echo_output
@cached
def server_access():
    """returns True if this builder instance has access to the master server.
    access may be available through presence of the master-server's bootstrap user's
    identify file OR current user is in master server's allowed_keys list"""
    stackname = core.find_master(core.find_region())
    public_ip = core.stack_data(stackname, ensure_single_instance=True)[0]['ip_address']
    result = local('ssh -o "StrictHostKeyChecking no" %s@%s "exit"' % (config.BOOTSTRAP_USER, public_ip))
    return result.return_code == 0

@echo_output
def aws_update_many_projects(pname_list):
    minions = ' or '.join(map(lambda pname: pname + "-*", pname_list))
    region = aws.find_region()
    with core.stack_conn(core.find_master(region)):
        sudo("salt -C '%s' state.highstate --retcode-passthrough" % minions)

@debugtask
@requires_project
def aws_update_projects(pname):
    "calls state.highstate on ALL projects matching <projectname>-*"
    return aws_update_many_projects([pname])

@debugtask
@requires_aws_stack
def remaster_minion(stackname, master_ip=None):
    "tell minion who their new master is. deletes any existing master key on minion"

    if not master_ip:
        newest_master = last(core.find_master_servers(core.active_aws_stacks(core.find_region())))
        if not newest_master:
            raise core.NoMasterException("no master servers found")
        master_ip = core.stack_data(newest_master)[0]['private_ip_address']

    print 're-mastering %s to %s' % (stackname, master_ip)

    def work():
        sudo("rm -f /etc/salt/pki/minion/minion_master.pub")  # destroy the old master key we have
        sudo("sed -i -e 's/^master:.*$/master: %s/g' /etc/salt/minion" % master_ip)
    core.stack_all_ec2_nodes(stackname, work, username=config.BOOTSTRAP_USER)
    bootstrap.update_ec2_stack(stackname, concurrency='serial')
