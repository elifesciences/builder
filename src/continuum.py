import os
import cfn
from fabric.api import run, task
from fabric.context_managers import cd
from decorators import requires_aws_project_stack, echo_output
from buildercore import core

@task
@requires_aws_project_stack('lax')
def lax_backfill(stackname):
    with core.stack_conn(stackname):
        # TODO: run this in a screen session but also figure out how to ctrl-c it
        with cd('/opt/bot-lax-adaptor/'):
            run('./backfill.sh')

@task
@requires_aws_project_stack('observer')
def observer_backfill(stackname):
    with core.stack_conn(stackname), cd('/srv/observer/'):
        run('./manage.sh load_from_api')

@task
@echo_output
def adhoc_instances():
    def unrecognised(stackname):
        iid = stackname.split('--')[-1]
        return iid not in ['ci', 'end2end', 'prod', 'continuumtest']
    import aws
    region = aws.find_region()
    return filter(unrecognised, core.active_stack_names(region))

@task
def daily_update_logs(*stacknames):
    path = "/var/log/daily-system-update.log"
    for stackname in stacknames:
        destpath = "%s--%s" % (stackname, os.path.basename(path))
        cfn.download_file(stackname, path, destpath)
