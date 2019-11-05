from buildercore.command import rcd, remote
from buildercore.core import stack_conn
from decorators import requires_aws_project_stack

@requires_aws_project_stack('elife-metrics')
def regenerate_results(stackname):
    with stack_conn(stackname):
        with rcd("/srv/elife-metrics/"):
            remote('./import-all-metrics.sh')
