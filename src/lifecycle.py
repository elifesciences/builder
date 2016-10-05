from fabric.api import task
from buildercore import lifecycle
from decorators import requires_aws_stack, timeit, echo_output, debugtask

@task
@requires_aws_stack
@timeit
def start(stackname):
    "Starts the nodes of 'stackname'. Idempotent"
    lifecycle.start(stackname)

@task
@requires_aws_stack
@timeit
def stop(stackname):
    "Stops the nodes of 'stackname' without losing their state. Idempotent"
    lifecycle.stop(stackname)

@task
@requires_aws_stack
@echo_output
def last_start_time(stackname):
    return lifecycle.last_start_time(stackname)

@task
@requires_aws_stack
@timeit
def stop_if_next_hour_is_imminent(stackname, minimum_minutes='55'):
    # TODO: can we write a description of the @task somewhere?
    """If a node has been running for a time between X:55:00 and X:59:59 hours, stops it to avoid incurring in a new charge for the next hour.
    
    The assumption is that stacks where this command is used are not needed for long parts of the day/week, and that who needs them will call the start task first."""
    return lifecycle.stop_if_next_hour_is_imminent(stackname, int(minimum_minutes))

@debugtask
@requires_aws_stack
def update_dns(stackname):
    lifecycle.update_dns(stackname)
