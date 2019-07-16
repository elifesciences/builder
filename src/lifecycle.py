import os
import json
import time, tempfile
from fabric.api import task
from buildercore import lifecycle, core
from utils import get_input
from buildercore.utils import splitfilter
from decorators import requires_aws_stack, timeit, debugtask, echo_output
import logging

LOG = logging.getLogger(__name__)

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
    if not services:
        services = ['ec2']

    lifecycle.stop(stackname, services)

@task
@requires_aws_stack
@timeit
@echo_output
def restart(stackname):
    return lifecycle.restart(stackname)


@task
def restart_all(statefile):
    "restarts all running ec2 instances. multiple nodes are restarted serially and failures prevent the rest of the node from being restarted"

    os.system("touch " + statefile)
    
    results = core.active_stack_names(core.find_region())

    u1404 = [
        'api-gateway',
        'journal',
        'search',
        'api-dummy',
        'medium',
    ]

    legacy = [
        'elife-api'
    ]
    
    dont_do = u1404 + legacy

    # order not preserved
    do_first = [
        'master-server',
        'bus',
        'elife-alfred',
        'elife-bot',
        'iiif',
    ]

    pname = lambda stackname: core.parse_stackname(stackname)[0]
    todo = sorted(results, key=lambda stackname: pname(stackname) in do_first, reverse=True)
    todo = filter(lambda stackname: pname(stackname) not in dont_do, todo)

    print('todo:')
    print(json.dumps(todo,indent=4))

    with open(statefile, 'r') as fh:
        done = fh.read().split('\n')

    todo = ['bioprotocol--end2end']
        
    with open(statefile, 'a') as fh:
        print('writing state to',fh.name)

        for stackname in todo:
            if stackname in done:
                print('skipping',stackname)
                continue
            try:
                print('restarting',stackname)
                # only restart instances that are currently running
                # this will skip ci/end2end
                lifecycle.restart(stackname, initial_states='running') 
                #time.sleep(2)
                print('done',stackname)
                fh.write(stackname + "\n")
                fh.flush()
            
            except:
                LOG.exception("unhandled exception restarting %s", stackname)
                print(stackname,"is in an unknown state")
                get_input('pausing, any key to continue, ctrl+c to quit')

        print
        print('wrote state to',fh.name)                

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
