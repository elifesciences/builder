import sys, os, traceback
import cfn, lifecycle, masterless, vault, aws, metrics, tasks, master, askmaster, buildvars, project, deploy
from decorators import echo_output

@echo_output
def ping():
    return "pong"

@echo_output
def echo(msg, *args, **kwargs):
    if args or kwargs:
        return "received: %s with args: %s and kwargs: %s" % (msg, args, kwargs)
    return "received: %s" % (msg,)


# 'unqualified' tasks are those that can be called just by their function name.
# for example: './bldr start' is the unqualified function 'lifecycle.start'
UNQUALIFIED_TASK_LIST = [
    ping, echo,

    cfn.destroy,
    cfn.ensure_destroyed,
    cfn.update,
    cfn.update_infrastructure,
    cfn.launch,
    cfn.ssh,
    cfn.owner_ssh,
    cfn.download_file,
    cfn.upload_file,
    cfn.cmd,

    deploy.switch_revision_update_instance,

    lifecycle.start,
    lifecycle.stop,
    lifecycle.restart,
    lifecycle.stop_if_running_for,
    lifecycle.update_dns,
]

# these are 'qualified' tasks where the full path to the function must be used
# for example: './bldr buildvars.switch_revision'
TASK_LIST = [
    metrics.regenerate_results, # todo: remove

    tasks.create_ami,
    tasks.repair_cfn_info,
    tasks.repair_context,
    tasks.remove_minion_key,
    tasks.restart_all_running_ec2,

    master.update,

    askmaster.fail2ban_running,
    askmaster.installed_linux_kernel,
    askmaster.linux_distro,
    askmaster.update_kernel,

    buildvars.switch_revision,

    project.data,
    project.context,
    project.new,

    masterless.launch,
    masterless.set_versions,

    vault.login,
    vault.logout,
    vault.policies_update,
    vault.token_lookup,
    vault.token_list_accessors,
    vault.token_lookup_accessor,
    vault.token_create,
    vault.token_revoke,
]

# 'debug' tasks are those that are available when the environment variable BLDR_ROLE is set to 'admin'
# this list of debug tasks don't require the full path to be used
# for example: 'BLDR_ROLE=admin ./bldr highstate' will execute the 'highstate'
UNQUALIFIED_DEBUG_TASK_LIST = [
    cfn.highstate,
    cfn.pillar,
    cfn.aws_stack_list,
]

# same as above, but the task name must be fully written out
# for example: 'BLDR_ROLE=admin ./bldr master.download_keypair'
DEBUG_TASK_LIST = [
    aws.rds_snapshots,
    aws.detailed_stack_list,

    tasks.diff_builder_config,

    deploy.load_balancer_status,
    deploy.load_balancer_register_all,

    master.write_missing_keypairs_to_s3,
    master.download_keypair,
    master.server_access,
    master.remaster,
    master.update_salt,
    master.update_salt_master,
    master.remaster_all,

    buildvars.read,
    buildvars.valid,
    buildvars.fix,
    buildvars.force,
]

def mk_task_map(task, qualified=True):
    """returns a map of information about the given task function.
    when `qualified` is `False`, the path to the task is truncated to just the task name"""
    path = "%s.%s" % (task.__module__.split('.')[-1], task.__name__)
    unqualified_path = task.__name__
    description = (task.__doc__ or '').strip().replace('\n', ' ')[:60]
    return {
        "name": path if qualified else unqualified_path,
        "path": path,
        "description": description,
        "fn": task,
    }

def generate_task_list(show_debug_tasks=False):
    """returns a collated list of maps with task information.

    [{"name": "fn", "fn": pathto.fn1, "description": "foo bar baz"}, ...]
     {"name": "pathto.fn", "fn": pathto.fn2, "description": "foo bar baz"}, ...]"""

    def to_list(task_list, qualified=True):
        return [mk_task_map(task, qualified) for task in task_list]

    new_task_list = to_list(UNQUALIFIED_TASK_LIST, qualified=False) + to_list(TASK_LIST)
    if show_debug_tasks:
        new_task_list = to_list(UNQUALIFIED_TASK_LIST, qualified=False) + \
            to_list(UNQUALIFIED_DEBUG_TASK_LIST) + \
            to_list(TASK_LIST) + \
            to_list(DEBUG_TASK_LIST)

    return new_task_list

# --- taken from Fabric3 (fork of Fabric 1, BSD Licenced)
# --- https://github.com/mathiasertl/fabric/blob/1.13.1/fabric/main.py#L499-L564
def _escape_split(sep, argstr):
    """
    Allows for escaping of the separator: e.g. task:arg='foo\, bar'

    It should be noted that the way bash et. al. do command line parsing, those
    single quotes are required.
    """
    escaped_sep = r'\%s' % sep

    if escaped_sep not in argstr:
        return argstr.split(sep)

    before, _, after = argstr.partition(escaped_sep)
    startlist = before.split(sep)  # a regular split is fine here
    unfinished = startlist[-1]
    startlist = startlist[:-1]

    # recurse because there may be more escaped separators
    endlist = _escape_split(sep, after)

    # finish building the escaped value. we use endlist[0] becaue the first
    # part of the string sent in recursion is the rest of the escaped value.
    unfinished += sep + endlist[0]

    return startlist + [unfinished] + endlist[1:]  # put together all the parts

def parse_arguments(arguments):
    """
    Parse string list into list of tuples: command, args, kwargs, hosts, roles.

    See sites/docs/usage/fab.rst, section on "per-task arguments" for details.
    """
    cmds = []
    for cmd in arguments:
        args = []
        kwargs = {}
        if ':' in cmd:
            cmd, argstr = cmd.split(':', 1)
            for pair in _escape_split(',', argstr):
                result = _escape_split('=', pair)
                if len(result) > 1:
                    k, v = result
                    kwargs[k] = v
                else:
                    args.append(result[0])
        cmds.append((cmd, args, kwargs))
    return cmds

# --- end

def exec_task(task_str, task_map_list):

    task_name, task_args, task_kwargs = parse_arguments([task_str])[0]

    return_map = {
        'task': task_name,
        'task_args': task_args,
        'task_kwargs': task_kwargs
    }

    task_map_list = [t for t in task_map_list if t['name'] == task_name]
    if not task_map_list:
        print("Command not found: %r" % task_name)
        return_map['rc'] = 1
        return return_map

    try:
        task_map = task_map_list[0]
        return_map['result'] = task_map['fn'](*task_args, **task_kwargs)
        return_map['rc'] = 0
        return return_map

    except KeyboardInterrupt:
        print('\nStopped.') # mimic fabric
        return_map['rc'] = 1
        return return_map

    except BaseException as e:
        print('exception while executing task %r: %s\n' % (task_name, str(e)))
        print(traceback.format_exc())
        return_map['rc'] = 2 # arbitrary
        return return_map

def main(arg_list):
    show_debug_tasks = os.environ.get("BLDR_ROLE") == "admin"
    task_map_list = generate_task_list(show_debug_tasks)

    if not arg_list or arg_list[1:]:
        print("`taskrunner.main` must be called from the ./bldr script")
        return 1

    # bash hands us an escaped string value via ./bldr
    command_string = arg_list[0].strip()

    if not command_string or command_string in ["-l", "--list", "-h", "--help", "-?"]:
        print("Available commands:\n")
        indent = 4
        for tm in task_map_list:
            path_len = len(tm['name'])
            max_path_len = 35
            offset = (max_path_len - path_len) + 2
            print("%s%s%s%s" % (' ' * indent, tm['name'], ' ' * offset, tm['description']))
        return 0

    task_result = exec_task(command_string, task_map_list)
    return task_result['rc']

if __name__ == '__main__':
    exit(main(sys.argv[1:]))
