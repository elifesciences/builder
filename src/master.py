"""Tasks we perform on the master server.

See `askmaster.py` for tasks that are run on minions."""

import os
import aws
from fabric.api import sudo, task, local
from buildercore import core, bootstrap, config, keypair
from decorators import debugtask, echo_output, requires_project, requires_aws_stack, requires_feature

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
def remaster_minion(stackname):
    """tell minion who their new master is.

    deletes the master's key on the minion
    updates the minion, which re-writes the minion config and eventually calls highstate

    * assumes you don't have ssh access to the minion
    * assumes writing keypairs to S3 is turned on"""
    print 're-mastering', stackname
    expected_key = core.stack_pem(stackname)
    if not os.path.exists(expected_key):
        download_keypair(stackname)
    with core.stack_conn(stackname, username=config.BOOTSTRAP_USER):
        sudo("rm -f /etc/salt/pki/minion/minion_master.pub")  # destroy the old master key we have
    bootstrap.update_stack(stackname)

@debugtask
def remaster_minions():
    map(remaster_minion, core.active_stack_names(aws.find_region()))

@task
def kick():
    stackname = core.find_master(core.find_region())
    with core.stack_conn(stackname, user=config.BOOTSTRAP_USER):
        bootstrap.run_script('kick-master.sh')
