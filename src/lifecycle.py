from fabric.api import task
from buildercore import lifecycle
from decorators import requires_aws_stack, timeit

@task
@requires_aws_stack
@timeit
def start(stackname):
    lifecycle.start(stackname)

@task
@requires_aws_stack
@timeit
def stop(stackname):
    lifecycle.stop(stackname)
