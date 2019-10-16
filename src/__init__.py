from shlex import shlex
import sys, os
import cfn, lifecycle, masterless, vault, aws, metrics, tasks, master, askmaster, buildvars, project, deploy
from buildercore.utils import splitfilter

unqualified_task_list = [
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

task_list = [
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

unqualified_debug_task_list = [
    cfn.highstate,
    cfn.pillar,
    cfn.aws_stack_list,
]

debug_task_list = [
    aws.rds_snapshots,
    aws.detailed_stack_list,

    tasks.diff_builder_config,

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

def task_map(task, qualified=True):
    path = "%s.%s" % (task.__module__.split('.')[-1], task.__name__)
    unqualified_path = task.__name__
    description = (task.__doc__ or '').replace('    ', '').replace('\n', ' ')[:60]
    return {
        "name": path if qualified else unqualified_path,
        "path": path,
        "description": description,
        "fn": task,
    }

def generate_task_list(show_debug_tasks):
    """returns a collated list of maps with task information.

    [{"name": "fn", "fn": pathto.fn1, "description": "foo bar baz"}, ...]
     {"name": "pathto.fn", "fn": pathto.fn2, "description": "foo bar baz"}, ...]"""

    def to_list(task_list, qualified=True):
        return [task_map(task, qualified) for task in task_list]

    new_task_list = to_list(unqualified_task_list, qualified=False) + to_list(task_list)
    if show_debug_tasks:
        new_task_list = to_list(unqualified_task_list, qualified=False) + \
            to_list(unqualified_debug_task_list) + \
            to_list(task_list) + \
            to_list(debug_task_list)

    return new_task_list

# taken from:
# https://stackoverflow.com/questions/38737250/extracting-key-value-pairs-from-string-with-quotes#answer-38738997
def parse_kv_pairs(text, item_sep=",", value_sep="="):
    """Parse key-value pairs from a shell-like text."""
    # initialize a lexer, in POSIX mode (to properly handle escaping)
    lexer = shlex(text, posix=True)
    # set ',' as whitespace for the lexer
    # (the lexer will use this character to separate words)
    lexer.whitespace = item_sep

    # include '=' as a word character
    # (this is done so that the lexer returns a list of key-value pairs)
    # (if your option key or value contains any unquoted special character, you will need to add it here)
    # https://docs.python.org/2/library/shlex.html#shlex.shlex.wordchars
    lexer.wordchars += value_sep
    lexer.wordchars += "-"

    # then we separate option keys and values to build the resulting dictionary
    # (maxsplit is required to make sure that '=' in value will not be a problem)

    # "param" => "param", "key=val" => ["key" "val"]
    def split_word_or_not(word):
        if value_sep in word:
            maxsplit = 1
            return word.split(value_sep, maxsplit)
        return word

    # => ["param1" "param2"],  [["key" "val"] ["foo" "bar"]]
    args, kwargs = splitfilter(lambda x: not isinstance(x, list), map(split_word_or_not, lexer))
    kwargs = dict(kwargs) # => {"key": "val", "foo": "bar"}
    return args, kwargs

def parse_task_string(task_str):
    """given task will look like 'taskname' or 'taskname:param1,param2' and each parameter may be either 'value' or 'key=value'
    a pair of [args, kwargs] is returned. both may be empty."""
    args = []
    kwargs = {}

    task_arg_separator_pos = task_str.find(":")
    if task_arg_separator_pos == -1:
        return task_str, args, kwargs

    task_name = task_str[:task_arg_separator_pos] # "taskname:foo,bar" => "taskname"
    task_args = task_str[task_arg_separator_pos + 1:] # => "foo,bar"
    args, kwargs = parse_kv_pairs(task_args)

    # print('task',task_str)
    #print('task args', args)
    #print('task kwargs', kwargs)

    return task_name, args, kwargs

def exec_task(task_str, task_map_list):

    task_name, task_args, task_kwargs = parse_task_string(task_str)

    return_map = {
        'task': task_name,
        'task_args': task_args,
        'task_kwargs': task_kwargs
    }

    task_map_list = [t for t in task_map_list if t['name'] == task_name]
    if not task_map_list:
        print("task %r not found" % task_name)
        return_map['rc'] = 1
        return return_map

    try:
        task_map = task_map_list[0]
        task_map['fn'](*task_args, **task_kwargs)
        return_map['rc'] = 0
        return return_map

    except BaseException as e:
        print('exception while executing task %r: %s' % (task_name, str(e)))
        # TODO: print stacktrace
        return_map['rc'] = 2 # I guess?
        return return_map

def main(arg_list):
    show_debug_tasks = os.environ.get("BLDR_ROLE") == "admin"
    task_map_list = generate_task_list(show_debug_tasks)

    if not arg_list or arg_list[1:]:
        print("builder should be called from the 'bldr' script") # or with a single double quoted argument string
        return 1

    command_string = arg_list[0].strip()

    if not command_string:
        for tm in task_map_list:
            path_len = len(tm['name'])
            max_path_len = 35
            offset = (max_path_len - path_len) + 2
            print("%s%s%s" % (tm['name'], ' ' * offset, tm['description']))
        return 0

    # TODO: do we have cases where we rely on running multiple tasks in one go?
    task_list = command_string.split(' ')
    task_result_list = [exec_task(task_str, task_map_list) for task_str in task_list]

    return sum([task_result['rc'] for task_result in task_result_list])

if __name__ == '__main__':
    exit(main(sys.argv[1:]))
