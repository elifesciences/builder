
"""

all of this code is now DEPRECATED. use `./bldr deploy` to deploy a branch.

I'll be scavving some of this code for general purpose branch-deployed projects later

"""

import json, time
import aws, utils
from fabric.api import task, settings, run, sudo, cd
from buildercore import core
from buildercore.config import DEPLOY_USER
from fabric.contrib import files
from decorators import requires_aws_project_stack

def unique_ext():
    return int(time.time() * 1000000)

@task
@requires_aws_project_stack('elife-website')
def update_buildvars(stackname, new_branch=None):
    project_name = core.project_name_from_stackname(stackname)
    
    buildvars = '/etc/build_vars.json'
    buildvarsb64 = '/etc/build_vars.json.b64'
    
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']
    with settings(user=DEPLOY_USER, host_string=public_ip, key_filename=aws.deploy_user_pem()):
        if files.exists(buildvarsb64):
            cmd = 'cat %s | base64 --decode' % buildvarsb64
            out = sudo(cmd)
            try:
                build_var_data = json.loads(out)
            except ValueError:
                print 'failed to decode json'

            new_branch = new_branch or utils.uin('branch')
            build_var_data[project_name]['branch'] = new_branch

            cmds = [
                # create a backup
                "cp %s %s.%s" % (buildvars, buildvars, unique_ext()),
                # output new data
                "echo '%s' > %s" % (json.dumps(build_var_data), buildvars),
            ]
            map(sudo, cmds)
            
        else:
            print 'remote file %s not found, quitting' % buildvarsb64

@task
@requires_aws_project_stack('elife-website')
def switch_branch(stackname):
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']  
    with settings(user=DEPLOY_USER, host_string=public_ip, key_filename=aws.deploy_user_pem()):
        with cd("/srv/website"):
            cmd = "git branch -a"
            output = run(cmd)
            x = output.splitlines()
            current_branch = filter(lambda l: l.startswith('*'), x)[0].strip(' *')
            x = map(lambda l: l.strip(' *'), x)
            
            print 'current branch:',current_branch
            new_branch = utils._pick("branch", x)
            run("git checkout -B %s" % new_branch)
            return new_branch

@task
@requires_aws_project_stack('elife-website')
def switch_remote_origin(stackname):
    "switches the remote origin of the targeted elife-drupal project"
    public_ip = aws.describe_stack(stackname)['instance']['ip_address']  
    with settings(user=DEPLOY_USER, host_string=public_ip, key_filename=aws.deploy_user_pem()):
        with cd("/srv/website/"):
            print 'current remote:'
            run("git remote -v")
            fork_list = [
                "git@github.com:thewilkybarkid/elife-website",
                "git@github.com:nlisgo/elife-website",
            ]
            uin = utils._pick("fork", fork_list)
            run("git remote set-url origin %s" % uin)
            print 'new remote:'
            run("git remote -v")
            print
            utils.git_purge(as_sudo=True)
            run('git config --global user.email "l.skibinski@elifesciences.org"')
            run('git config --global user.name "elife-bot"')
            run('git config --global color.ui off')
            run('git checkout master')
            run('git fetch')
            #utils.git_update()

@task
@requires_aws_project_stack('elife-website')
def switch(stackname):
    switch_remote_origin(stackname)
    branch = switch_branch(stackname)
    update_buildvars(stackname, branch)
