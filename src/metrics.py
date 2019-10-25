from buildercore.command import cd, run
from buildercore.core import stack_conn
from decorators import requires_aws_project_stack

@requires_aws_project_stack('elife-metrics')
def regenerate_results(stackname):
    with stack_conn(stackname):
        with cd("/srv/elife-metrics/"):
            run('./import-all-metrics.sh')
