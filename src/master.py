"""Tasks we perform on the master server.

See `askmaster.py` for tasks that are run on minions."""

import os, time
import aws
from fabric.api import sudo, local
from buildercore import core, bootstrap, config, keypair, project, utils
from buildercore.utils import lmap, exsubdict
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
    local_keys = lmap(os.path.basename, local_paths)

    to_upload = set(local_keys).difference(set(remote_keys))

    print('remote:', remote_keys)
    print('local:', local_keys)
    print('to upload:', to_upload)

    def write(key):
        stackname = os.path.splitext(key)[0]
        keypair.write_keypair_to_s3(stackname)

    lmap(write, to_upload)

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
        LOG.info(err)

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
    minions = ' or '.join([pname + "-*" for pname in pname_list])
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
def remaster_minion(stackname, new_master_stackname):
    "tell minion who their new master is. deletes any existing master key on minion"
    # TODO: turn this into a decorator
    import cfn
    cfn._check_want_to_be_running(stackname, 1)

    master_ip = core.stack_data(new_master_stackname)[0]['private_ip_address']

    print('re-mastering %s to %s' % (stackname, master_ip))

    def work():
        sudo("rm -f /etc/salt/pki/minion/minion_master.pub")  # destroy the old master key we have
        sudo("sed -i -e 's/^master:.*$/master: %s/g' /etc/salt/minion" % master_ip)
    core.stack_all_ec2_nodes(stackname, work, username=config.BOOTSTRAP_USER)
    context = None # will be supplied for us
    bootstrap.update_ec2_stack(stackname, context, concurrency='serial', master_ip=master_ip)

@debugtask
@requires_aws_stack
def remaster_all_minions(new_master_stackname):
    import cfn
    LOG.info('new master is: %s', new_master_stackname)
    ec2stacks = project.ec2_projects()
    ignore = [
        'master-server',
        'jats4r',
    ]
    ec2stacks = exsubdict(ec2stacks, ignore)
    pname_list = sorted(ec2stacks.keys()) # lets do this alphabetically

    # only update ec2 instances in the same region as the new master
    region = aws.find_region(new_master_stackname)
    active_stacks = core.active_stack_names(region)
    stack_idx = utils.mkidx(lambda v: core.parse_stackname(v)[0], active_stacks)

    def sortbyenv(n):
        adhoc = 0 # do these first
        order = {
            'continuumtest': 1,
            'ci': 2,
            'end2end': 3,
            'prod': 4, # update prod last
        }
        return order.get(core.parse_stackname(n)[-1], adhoc)

    remastered_list = open('remastered.txt', 'r').readlines() if os.path.exists('remastered.txt') else []
    for pname in pname_list:
        if pname not in stack_idx:
            continue
        stack_list = sorted(stack_idx[pname], key=sortbyenv)
        LOG.info("%r instances: %s" % (pname, ", ".join(stack_list)))
        try:
            for stackname in stack_list:
                try:
                    if stackname in remastered_list:
                        LOG.info("already updated, skipping stack: %s", stackname)
                        continue
                    LOG.info("*" * 80)
                    LOG.info("updating: %s" % stackname)
                    cfn.update_template(stackname)
                    remaster_minion(stackname, new_master_stackname)
                    open('remastered.txt', 'a').write("%s\n" % stackname)
                except KeyboardInterrupt:
                    LOG.warn("ctrl-c, skipping stack: %s", stackname)
                    time.sleep(1)
                except BaseException:
                    LOG.exception("unhandled exception updating stack: %s", stackname)
        except KeyboardInterrupt:
            LOG.warn("quitting")
            break

    LOG.info("wrote 'remastered.txt'")
