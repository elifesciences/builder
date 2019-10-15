import sys, os
import cfn, lifecycle, masterless, vault, aws, metrics, tasks, master, askmaster, buildvars, project, deploy

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

def generate_task_list(show_debug_tasks):
    """returns a collated list of maps with task information 
    
    [{"name": "fn", "fn": pathto.fn1, "desc": "foo bar baz"}, ...]
     {"name": "pathto.fn", "fn": pathto.fn2, "desc": "foo bar baz"}, ...]"""

    def task_map(task, qualified=True):
        path = "%s.%s" % (task.__module__.split('.')[-1], task.__name__)
        unqualified_path = task.__name__
        description = (task.__doc__ or '').replace('    ', '').replace('\n', ' ')[:60]
        return {
            "name": path if qualified else unqualified_path,
            "description": description,
            "fn": task,
        }

    def to_list(task_list, qualified=True):
        return [task_map(task, qualified) for task in task_list]
    
    new_task_list = to_list(unqualified_task_list, qualified=False) + to_list(task_list)
    if show_debug_tasks:
        new_task_list = to_list(unqualified_task_list, qualified=False) + \
            to_list(unqualified_debug_task_list) + \
            to_list(task_list) + \
            to_list(debug_task_list)

    return new_task_list

def main(arg_list):
    show_debug_tasks = os.environ.get("BLDR_ROLE") == "admin"
    task_list = generate_task_list(show_debug_tasks)

    task = arg_list[0]
    
    if not task:
        for t in task_list:
            path_len = len(t['name'])
            max_path_len = 35
            offset = (max_path_len - path_len) + 2
            print("%s%s%s" % (t['name'], ' ' * offset, t['description']))
            
            #print((t['description'] or '')[:50 - tlen].ljust(70))
            #print("%s%+40s" % (t['name'], str(t['description'] or '')[:30]))
        return 0

    print('got args',arg_list)
    print('task:',task)

    # find given task in list of tasks
    # call task with list of parameters

    return 0

if __name__ == '__main__':
    exit(main(sys.argv[1:]))
