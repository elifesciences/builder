# import threadbare early so gevent.monkey_patch can patch everything
from buildercore import config, threadbare
from functools import reduce
from decorators import echo_output
from buildercore import command
import cfn, lifecycle, masterless, vault, aws, tasks, master, askmaster, buildvars, project, deploy, report, fix, checks, stack
import aws.rds, aws.cloudformation
import sys, traceback
import utils

# threadbare module is otherwise not used is flagged for linting
assert threadbare

@echo_output
def ping():
    return "pong"

@echo_output
def echo(msg, *args, **kwargs):
    if args or kwargs:
        return "received: %s with args: %s and kwargs: %s" % (msg, args, kwargs)
    return "received: %s" % (msg,)


# NOTE: 'unqualified' tasks are those that can be called just by their function name.
# for example: `./bldr start` is the unqualified function `lifecycle.start`
# NOTE: a task's function signature constitutes it's API, check twice before changing it.
# the 'see: ...' references below are *not* comprehensive.
UNQUALIFIED_TASK_LIST = [
    ping, echo, cfn.dev,

    cfn.destroy,
    # see: elife-jenkins-workflow-libs/vars/elifeFormula.groovy
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.basebox-1804, Jenkinsfile.clean-journal-environments
    cfn.ensure_destroyed,
    # see: elife-jenkins-workflow-libs/vars/builderUpdate.groovy, elifeFormula.groovy
    cfn.update,
    cfn.update_infrastructure,
    fix.fix_infrastructure,
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.basebox-1804, Jenkinsfile.update-journal-pr
    cfn.launch,
    cfn.ssh,
    cfn.owner_ssh,
    # see: elife-jenkins-workflow-libs/vars/builderTestArtifact.groovy
    cfn.download_file,
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.journal-cms-restore-continuumtest
    cfn.upload_file,
    # see: elife-jenkins-workflow-libs/vars/builderCmd*.groovy
    cfn.cmd,
    # see: elife-jenkins-workflow-libs/vars/builderDeployRevision.groovy
    deploy.switch_revision_update_instance,
    # see: elife-jenkins-workflow-libs/vars/builderStart.groovy
    lifecycle.start,
    # see: elife-jenkins-workflow-libs/vars/builderStop.groovy
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.basebox-1804, Jenkinsfile.ec2-plugin-ami-update
    lifecycle.stop,
    lifecycle.restart,
    # see: elife-jenkins-workflow-libs/vars/builderStopIfRunningFor.groovy
    lifecycle.stop_if_running_for,
    lifecycle.update_dns,
]

# NOTE: these are 'qualified' tasks where the full path to the function must be used.
# for example: `./bldr buildvars.switch_revision`
TASK_LIST = [
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.basebox-1804, Jenkinsfile.ec2-plugin-ami-update
    tasks.create_ami,
    tasks.repair_cfn_info,
    tasks.repair_context,
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.basebox-1804, Jenkinsfile.ec2-plugin-ami-update
    tasks.remove_minion_key,
    # see: elife-alfred-formula/jenkinsfiles/Jenkinsfile.master-server
    master.update,

    askmaster.fail2ban_running,
    askmaster.installed_linux_kernel,
    askmaster.linux_distro,
    askmaster.installed_salt_version,

    # see: elife-jenkins-workflow-libs/vars/builderRunAll.groovy
    buildvars.switch_revision,

    # see: journal/Jenkinsfile.prod
    deploy.load_balancer_register_all,

    project.data,
    project.context,
    project.new,

    stack.list,
    stack.config,

    # see: elife-jenkins-workflow-libs/vars/elifeFormula.groovy
    masterless.launch,
    # see: elife-jenkins-workflow-libs/vars/elifeFormula.groovy
    masterless.set_versions,

    vault.login,
    vault.logout,
    vault.policies_update,
    vault.token_lookup,
    vault.token_list_accessors,
    vault.token_lookup_accessor,
    vault.token_create,
    vault.token_revoke,

    report.all_projects,
    report.all_ec2_projects,
    report.all_ec2_instances,
    report.all_ec2_instances_for_salt_upgrade,
    report.all_rds_projects,
    report.all_rds_instances,
    report.all_formulas,
    report.all_adhoc_ec2_instances,
    report.long_running_large_ec2_instances,
    report.all_amis_to_prune,

    checks.stack_exists,
    tasks.delete_all_amis_to_prune,
]

# 'debug' tasks are those that are available when the environment variable BLDR_ROLE is set to 'admin'
# this list of debug tasks don't require the full path to be used
# for example: 'BLDR_ROLE=admin ./bldr highstate' will execute the 'highstate' task
UNQUALIFIED_DEBUG_TASK_LIST = [
    cfn.highstate,
    cfn.fix_bootstrap,
    cfn.pillar,
    # cfn.aws_stack_list, # moved to 'aws.cloudformation.stack_list'
]

# same as above, but the task name must be fully written out
# for example: 'BLDR_ROLE=admin ./bldr master.download_keypair'
DEBUG_TASK_LIST = [
    aws.rds.snapshot_list,
    aws.cloudformation.stack_list,

    deploy.load_balancer_status,

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
    buildvars.refresh,

    project.clone_project_formulas,
    project.clone_all_project_formulas,
]

def mk_task_map(task, qualified=True):
    """returns a map of information about the given task function.
    when `qualified` is `False`, the path to the task is truncated to just the task name"""
    # lsh@2022-09-16: not sure why I was truncating the module path ('aws.rds' => 'rds'),
    # but I need the full thing now.
    #path = "%s.%s" % (task.__module__.split('.')[-1], task.__name__)
    path = "%s.%s" % (task.__module__, task.__name__)
    unqualified_path = task.__name__
    #description = (task.__doc__ or '').strip().replace('\n', ' ')
    docstr = (task.__doc__ or '').replace('  ', '')
    docstr_bits = docstr.split('\n', 1)
    short_str = docstr_bits[0]
    more_str = docstr_bits[1] if len(docstr_bits) > 1 else ''
    return {
        "name": path if qualified else unqualified_path,
        "path": path,
        "description": short_str,
        "docstr": docstr,
        "long_description": more_str,
        "fn": task,
    }

def generate_task_list(show_debug_tasks=False):
    """returns a collated list of maps with task information.

    [{"name": "ssh", "fn": cfn.ssh, "description": "foobar baz"}, ...]
     {"name": "cfn.deploy", "fn": cfn.deploy, "description": "bar barbar"}, ...]"""

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
    # autopep8 wants to format "r'foo\" to "r'foo\\"
    # fmt: off
    """
    Allows for escaping of the separator: e.g. task:arg=r'foo\, bar' (ignore leading 'r')

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

    except utils.TaskExit as te:
        msg = str(te)
        if msg:
            print(msg)
        print('\nQuit.')
        return_map['rc'] = 1
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

    finally:
        # close any outstanding network connections
        command.network_disconnect_all()

def main(arg_list):
    show_debug_tasks = config.ENV["BLDR_ROLE"] == "admin"
    task_map_list = generate_task_list(show_debug_tasks)

    if not arg_list or arg_list[1:]:
        print("`taskrunner.main` must be called from the ./bldr script")
        return 1

    # bash hands us an escaped string value via ./bldr
    command_string = arg_list[0].strip()

    # print('this is what we see after bash:')
    # print(command_string)

    if not command_string or command_string in ["-l", "--list"]:
        print("Available commands:\n")
        indent = 2
        max_path_len = reduce(max, [len(tm['name']) for tm in task_map_list])
        task_description_gap = 2
        #max_description_len = 70
        for tm in task_map_list:
            path_len = len(tm['name'])
            offset = (max_path_len - path_len) + task_description_gap
            offset_str = ' ' * offset
            task_name = tm['name']
            leading_indent = ' ' * indent
            new_indent = ' ' * (indent + len(task_name) + offset)

            print(leading_indent + task_name + offset_str + tm['description'])
            for row in tm['long_description'].split('\n'):
                row = row.strip()
                if not row:
                    continue
                print(new_indent + row)

            if tm['long_description']:
                print()

        # no explicit invocation of help gets you an error code
        return 0 if command_string else 1

    task_result = exec_task(command_string, task_map_list)
    return task_result['rc']

if __name__ == '__main__':
    exit(main(sys.argv[1:]))
