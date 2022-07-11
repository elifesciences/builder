"""Tasks we perform on the master server.

See `askmaster.py` for tasks that are run on minions."""

import os, time
import cfn, buildvars, utils
from buildercore.command import remote_sudo, local
from buildercore import core, bootstrap, config, keypair, project, cfngen, context_handler
from buildercore.utils import lmap, exsubdict, mkidx
from decorators import echo_output, requires_aws_stack
from kids.cache import cache as cached
import logging

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
    except EnvironmentError as err:
        LOG.info(err)

#
#
#

@echo_output
@cached
def server_access():
    """returns True if this builder instance has access to the master server.
    access may be available through presence of the master-server's bootstrap user's
    identify file OR current user is in master server's allowed_keys list"""
    stackname = core.find_master(core.find_region())
    public_ip = core.stack_data(stackname, ensure_single_instance=True)[0]['PublicIpAddress']
    result = local('ssh -o "StrictHostKeyChecking no" %s@%s "exit"' % (config.BOOTSTRAP_USER, public_ip))
    return result['succeeded']

# @cached
# def _cached_master_ip(master_stackname):
#    "provides a small time saving when remastering many minions"
#    return core.stack_data(master_stackname)[0]['PrivateIpAddress']

@requires_aws_stack
def update_salt(stackname):
    "updates the Salt version installed on the instances for the given stack"

    # start instance if it is stopped
    # acquire a lock from Alfred (if possible) so instance isn't shutdown while being updated
    cfn._check_want_to_be_running(stackname, autostart=True)

    context = context_handler.load_context(stackname)

    if not context.get('ec2'):
        LOG.info("no ec2 context. skipping stack: %s", stackname)
        return

    LOG.info("upgrading stack's salt minion")

    pdata = core.project_data_for_stackname(stackname)
    context['project']['salt'] = pdata['salt']

    LOG.info("updating stack's context")
    context_handler.write_context(stackname, context)

    LOG.info("updating stack's nodes (sequentially)")
    bootstrap.update_ec2_stack(stackname, context, concurrency='serial')
    return True

def update_salt_master(region=None):
    "convenience. update the version of Salt installed on the master-server."
    region = region or utils.find_region()
    current_master_stackname = core.find_master(region)
    return update_salt(current_master_stackname)

@requires_aws_stack
def remaster(stackname, new_master_stackname="master-server--prod", skip_context_check=False):
    "tell minion who their new master is. deletes any existing master key on minion"
    skip_context_check = utils.strtobool(skip_context_check)
    # start instance if it is stopped
    # acquire a lock from Alfred (if possible) so instance isn't shutdown while being updated
    cfn._check_want_to_be_running(stackname, autostart=True)

    #master_ip = _cached_master_ip(new_master_stackname)
    master_ip = "prod--master-server.elife.internal"
    LOG.info('re-mastering %r to %r', stackname, master_ip)

    context = context_handler.load_context(stackname)

    if not context.get('ec2'):
        LOG.info("no ec2 context, skipping %s", stackname)
        return

    if context['ec2'].get('master_ip') == master_ip:
        LOG.info("already remastered: %s", stackname)
        if not skip_context_check:
            return

    pdata = core.project_data_for_stackname(stackname)

    LOG.info("setting new master address")
    cfngen.set_master_address(pdata, context, master_ip) # mutates context

    LOG.info("updating context")
    context_handler.write_context(stackname, context)

    LOG.info("updating buildvars")
    buildvars.refresh(stackname, context)

    # remove knowledge of old master by destroying the minion's master pubkey
    def workerfn():
        remote_sudo("rm -f /etc/salt/pki/minion/minion_master.pub")
    LOG.info("removing old master key from minion")
    core.stack_all_ec2_nodes(stackname, workerfn, username=config.BOOTSTRAP_USER)

    LOG.info("updating nodes")

    bootstrap.update_ec2_stack(stackname, context, concurrency='serial', dry_run=True)
    return True

def remaster_all(*pname_list, prompt=False, skip_context_check=False):
    "calls `remaster` on *all* projects or just a subset of projects"

    ignore_pname = [
        'master-server',
        'basebox',
        'heavybox',
        'large-repo-wrangler',
    ]

    ignore_stackname = [
        'pattern-library--ci',
    ]

    prompt = utils.strtobool(prompt)
    skip_context_check = utils.strtobool(skip_context_check)

    # there should only be one master-server instance at a time.
    # multiple masters is bad news. assumptions break and it gets complicated quickly.
    new_master_stackname = "master-server--prod"
    LOG.info('new master is: %s', new_master_stackname)
    ec2stacks = project.ec2_projects()
    ec2stacks = exsubdict(ec2stacks, ignore_pname)

    # we can optionally pass in a list of projects to target
    # this allows us to partition up the projects and have many of these
    # remastering efforts happening concurrently
    if pname_list:
        more_ignore = [p for p in ec2stacks if p not in pname_list]
        ec2stacks = exsubdict(ec2stacks, more_ignore)

    pname_list = sorted(ec2stacks.keys()) # lets do this alphabetically

    # only update ec2 instances in the same region as the new master
    region = utils.find_region(new_master_stackname)
    active_stacks = core.active_stack_names(region)
    stack_idx = mkidx(lambda v: core.parse_stackname(v)[0], active_stacks)

    def sortbyenv(n):
        adhoc = 0 # do these first
        order = {
            'continuumtest': 1,
            'ci': 2,
            'end2end': 3,
            'prod': 4, # update prod last
        }
        pname, iid = core.parse_stackname(n)
        return order.get(iid, adhoc)

    remastered_list = open('remastered.txt', 'r').read().splitlines() if os.path.exists('remastered.txt') else []

    for pname in pname_list:
        # when would this ever be the case?
        # `core.active_stack_names` doesn't discriminate against any list of projects
        # it returns *all* steady stack names.
        if pname not in stack_idx:
            continue

        project_stack_list = sorted(stack_idx[pname], key=sortbyenv)
        LOG.info("%r instances: %s" % (pname, ", ".join(project_stack_list)))
        try:
            for stackname in project_stack_list:
                if stackname in ignore_stackname:
                    continue

                try:
                    if stackname in remastered_list:
                        LOG.info("already updated, skipping stack: %s", stackname)
                        continue
                    LOG.info("*" * 80)
                    LOG.info("updating: %s" % stackname)
                    prompt and utils.get_input('continue? ctrl-c to quit')
                    if not remaster(stackname, new_master_stackname, skip_context_check):
                        LOG.warning("failed to remaster %s, stopping further remasters to project %r", stackname, pname)
                        break
                    # print a reminder of which stack was just updated
                    print("\n(%s)\n" % stackname)
                    open('remastered.txt', 'a').write("%s\n" % stackname)
                except KeyboardInterrupt:
                    LOG.warning("ctrl-c, skipping stack: %s", stackname)
                    LOG.info("ctrl-c again to exit process entirely")
                    time.sleep(2)
                except BaseException:
                    LOG.exception("unhandled exception updating stack: %s", stackname)
                    raise
        except KeyboardInterrupt:
            LOG.warning("quitting")
            break

    LOG.info("wrote 'remastered.txt'")
