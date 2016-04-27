from fabric.api import task, cd, settings, run
from aws import stack_conn
from decorators import requires_aws_project_stack
from buildercore.config import DEPLOY_USER

@task
@requires_aws_project_stack('elife-metrics')
def regenerate_results(stackname):
    with stack_conn(stackname):
        with cd("/srv/elife-metrics/"):
            run('./import-all-metrics.sh')
