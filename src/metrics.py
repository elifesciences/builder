from fabric.api import task, cd, settings, run
from aws import describe_stack, deploy_user_pem
from decorators import requires_aws_project_stack
#from buildercore.config import ROOT_USER, DEPLOY_USER, BOOTSTRAP_USER, AUTO_STACK_PATH, STACK_PATH
from buildercore.config import DEPLOY_USER

@task
@requires_aws_project_stack('elife-metrics')
def regenerate_results(stackname):
    public_ip = describe_stack(stackname)['instance']['ip_address']
    with settings(user=DEPLOY_USER, host_string=public_ip, key_filename=deploy_user_pem()):
        with cd("/srv/elife-metrics/"):
            run('./import-all-metrics.sh')
