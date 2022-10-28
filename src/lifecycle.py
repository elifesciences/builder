import re
import report, utils
from buildercore import core, lifecycle
from decorators import requires_aws_stack, timeit, echo_output

@requires_aws_stack
@timeit
def start(stackname):
    "Starts the nodes of 'stackname'. Idempotent"
    lifecycle.start(stackname)

def start_many(pattern):
    if not pattern:
        raise utils.TaskExit("a regular expression matching ec2 names is required.")
    ec2_list = report._all_ec2_instances(state=None)
    filtered_ec2_list = filter(lambda ec2_name: re.match(pattern, ec2_name), ec2_list)
    [start(core.short_stackname_from_long_stackname(ec2)) for ec2 in filtered_ec2_list]

@requires_aws_stack
@timeit
def stop(stackname, *services):
    """Stops the nodes of 'stackname' without losing their state.
    Idempotent. Default to stopping only EC2 but additional services
    like 'rds' can be passed in"""
    if not services:
        services = ['ec2']
    lifecycle.stop(stackname, services)

@requires_aws_stack
@timeit
@echo_output
def restart(stackname):
    stop(stackname)
    start(stackname)

@requires_aws_stack
@timeit
def stop_if_running_for(stackname, minimum_minutes='30'):
    """Stops an ec2 node that has been running for too long.
    The assumption is that stacks where this command is used are not
    needed for long parts of the day/week, and that who needs them will
    call the start task first."""
    return lifecycle.stop_if_running_for(stackname, int(minimum_minutes))

@requires_aws_stack
def update_dns(stackname):
    """Updates the public DNS entry of the EC2 nodes.
    Private DNS entries typically do not need updates, and only
    EC2 nodes have public, mutable IP addresses during restarts."""
    lifecycle.update_dns(stackname)
