from fabric.api import task
from buildercore import lifecycle
from decorators import requires_aws_stack, timeit, debugtask

@task
@requires_aws_stack
@timeit
def start(stackname):
    "Starts the nodes of 'stackname'. Idempotent"
    lifecycle.start(stackname)

@task
@requires_aws_stack
@timeit
def stop(stackname, *services):
    """Stops the nodes of 'stackname' without losing their state.

    Idempotent. Default to stopping only EC2 but additional services like 'rds' can be passed in"""
    if services == []:
        services = ['ec2']

    lifecycle.stop(stackname, services)

@task
@requires_aws_stack
@timeit
def restart(stackname):
    stop(stackname)
    start(stackname)

@task
@requires_aws_stack
@timeit
def stop_if_running_for(stackname, minimum_minutes='30'):
    """If a EC2 node has been running for a time greater than minimum_minutes, stop it.

    The assumption is that stacks where this command is used are not needed for long parts of the day/week, and that who needs them will call the start task first."""
    return lifecycle.stop_if_running_for(stackname, int(minimum_minutes))

@debugtask
@requires_aws_stack
def update_dns(stackname):
    """Updates the public DNS entry of the EC2 nodes.

    Private DNS entries typically do not need updates, and only EC2 nodes have public, mutable IP addresses during restarts"""
    lifecycle.update_dns(stackname)
