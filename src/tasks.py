"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be
better off in their own module. This module really is for stuff
that has no home."""
import os
from buildercore import core, bootstrap
from fabric.api import sudo, run, local, task, cd
from fabric.operations import put as upload, get as download
from fabric.contrib.console import confirm
from fabric.contrib.files import exists as remote_file_exists
from decorators import echo_output, requires_aws_stack, requires_project, requires_aws_project_stack, debugtask
from buildercore import bakery
from buildercore.core import stack_conn
from buildercore.utils import ensure
import utils
from buildercore.context_handler import load_context

@debugtask
@requires_project
@echo_output
def ami_for_project(pname):
    "returns possible AMIs suitable for given project"
    conn = core.connect_aws_with_pname(pname, 'ec2')
    kwargs = {
        # you're better off just going here:
        # https://cloud-images.ubuntu.com/locator/ec2/
        # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeImages.html#query-DescribeImages-filters
        'filters': {
            #'root-device-type': 'ebs',
            #'virtualization_type': 'hvm',
            'architecture': 'x86_64',
            #'name': 'ubuntu/images/*',
            'name': 'ubuntu/images/*/*14.04*201605*',
            'state': 'available',
            'root-device-name': '/dev/sda1',
        },
        'owners': ['099720109477'] # Canonical
    }
    results = conn.get_all_images(**kwargs)

    print results

    print len(results), "results"

    return utils.table(results, ['id', 'root_device_type', 'virtualization_type', 'name'])

    # good for figuring out filters
    # print results[0].__dict__

@task
@requires_aws_stack
def create_ami(stackname):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r. Continue?" % pname
    if not confirm(msg, default=False):
        print 'doing nothing'
        return
    amiid = bakery.create_ami(stackname)
    print 'AWS has created AMI with id', amiid
    print 'update project file with new ami %s. these changes must be merged and committed manually' % amiid

@requires_aws_stack
def _update_syslog(stackname):
    with stack_conn(stackname):
        cmd = "salt-call state.sls_id syslog-ng-hook base.syslog-ng test=True"
        return sudo(cmd)

#
#
#

@debugtask
def diff_builder_config():
    "helps keep three"
    file_sets = [
        [
            "./builder-private-example/pillar/elife.sls",
            "./cloned-projects/builder-base-formula/pillar/elife.sls",
            "./builder-private/pillar/elife.sls"
        ],
        [
            "./projects/elife.yaml",
            "./builder-private/projects/elife-private.yaml",
        ]
    ]
    for paths in file_sets:
        local("meld " + " ".join(paths))

@task
@requires_aws_stack
def repair_cfn_info(stackname):
    with stack_conn(stackname):
        bootstrap.write_environment_info(stackname, overwrite=True)

@task
@requires_aws_stack
def repair_context(stackname):
    # triggers the workaround of downloading it from EC2 and persisting it
    load_context(stackname)

@task
@requires_aws_stack
def remove_minion_key(stackname):
    bootstrap.remove_minion_key(stackname)

#
#
#

@task
@requires_aws_project_stack('elife-bot')
def strip(stackname, pdffile):
    path, fname = os.path.abspath(pdffile), os.path.basename(pdffile)
    ensure(os.path.exists(path), "file not found: %s" % path)
    dest_path = '/home/elife/' + fname
    with stack_conn(stackname):
        if not remote_file_exists(dest_path):
            print "remote file not found, uploading"
            upload(path, dest_path)
        with cd('/opt/strip-coverletter'):
            out_path = '/home/elife/squashed-%s' % fname
            run('./strip-coverletter.sh %s %s' % (dest_path, out_path))
        if remote_file_exists(out_path):
            download(out_path, os.path.basename(out_path))
