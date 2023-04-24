from buildercore.utils import ensure, isint
from buildercore import core, lifecycle

def _find_node(node, node_obj_list):
    ensure(isint(node), "node value must be an integer")
    node = int(node)
    ensure(node > 0, "node value must be a non-zero integer")
    num_nodes = len(node_obj_list)
    ensure(num_nodes >= node, "stack has %s nodes but you want node %s" % (num_nodes, node))
    node_obj = node_obj_list[node - 1]
    return node_obj

def stop_node(stackname, node):
    """Unsafe. You probably want 'stop' ('lifecycle.stop').
    Stops an ec2 instance, polling until stopped.
    Does not check current state before attempting to stop (excluding terminated/terminating instances).
    Does not care if all other nodes are also unavailable."""
    node_obj_list = core.find_ec2_instances(stackname, state='pending|running|stopping|stopped')
    node_obj = _find_node(node, node_obj_list)
    node_ids = [node_obj.id]
    lifecycle._ec2_connection(stackname).instances.filter(InstanceIds=node_ids).stop()

    def poll_fn():
        return lifecycle._ec2_nodes_states(stackname, node_ids)

    lifecycle._wait_all_in_state(stackname, 'stopped', node_ids, poll_fn, 'EC2')

def start_node(stackname, node):
    """Unsafe. You probably want 'start' ('lifecycle.start').
    Starts the ec2 instance, polling until available.
    Does not check current state before attempting to start (excluding terminated/terminating instances).
    Does not check for errors booting.
    Does not update DNS."""
    node_obj_list = core.find_ec2_instances(stackname, state='pending|running|stopping|stopped')
    node_obj = _find_node(node, node_obj_list)
    node_ids = [node_obj.id]
    lifecycle._ec2_connection(stackname).instances.filter(InstanceIds=node_ids).start()

    def poll_fn():
        return lifecycle._ec2_nodes_states(stackname, node_ids)
    lifecycle._wait_all_in_state(stackname, 'running', node_ids, poll_fn, 'EC2')

def restart_node(stackname, node):
    """Unsafe. You probably want 'restart' ('lifecycle.restart').
    Stops an ec2 instance, polling until stopped, then starts the
    ec2 instance, polling until available.
    Does not check for errors booting.
    Does not care if all other nodes are also unavailable.
    Does not update DNS."""
    stop_node(stackname, node)
    start_node(stackname, node)

def reboot_node(stackname, node):
    """Unsafe. You probably want 'restart' ('lifecycle.restart').
    Stops and starts and ec2 instance with one command, not polling for
    the instance to stop before starting.
    Does not check for errors booting.
    Does not care if all other nodes are also unavailable.
    Does not update DNS.
    Does not wait for node to come back up, just triggers reboot and exits.
    Used to stop and start the machine the reboot command is being run on."""
    node_obj_list = core.find_ec2_instances(stackname, state='pending|running|stopping|stopped')
    node_obj = _find_node(node, node_obj_list)
    node_ids = [node_obj.id]
    lifecycle._ec2_connection(stackname).instances.filter(InstanceIds=node_ids).reboot()

    # unlike stop and start, the state of the instance after a reboot doesn't change from 'running'
    # so we can't do any polling. We just have to hope it goes down and comes back up :(
