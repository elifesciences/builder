import requests
from buildercore import core, cfngen, config, project
from buildercore.sync import sync_stack
from fabric.api import sudo, run, local, task
from decorators import echo_output, requires_aws_stack
from aws import stack_conn
import utils, aws
from buildercore.decorators import osissue, osissuefn

def salt_master_cmd(cmd, module='cmd.run', minions=r'\*'):
    "runs the given command on all aws instances. given command must escape double quotes"
    with stack_conn(core.find_master(aws.find_region())):
        sudo("salt %(minions)s %(module)s %(cmd)s --timeout=30" % locals())

@task
@echo_output
def cronjobs():
    "list the cronjobs running as elife on all instances"
    return salt_master_cmd("'crontab -l -u elife'")

@task
def daily_updates_enabled():
    return salt_master_cmd("'crontab -l | grep daily-system-update'")

@task
@echo_output
def syslog_conf():
    minions = "-C 'elife-metrics-* or elife-lax-* or elife-api-*'"
    return salt_master_cmd("'cat /etc/syslog-ng/syslog-ng.conf | grep use_fqdn'", minions=minions)

@task
@osissue("very specific code. possibly a once-off that can be deleted")
def update_syslog():
    module = 'state.sls_id'
    cmd = "syslog-ng-hook base.syslog-ng test=True"
    minions = 'elife-crm-production'
    return salt_master_cmd(cmd, module, minions)

@requires_aws_stack
def _update_syslog(stackname):
    with stack_conn(stackname):
        cmd = "salt-call state.sls_id syslog-ng-hook base.syslog-ng test=True"
        return sudo(cmd)

@task
def fail2ban_running():
    #return salt_master_cmd("'ps aux | grep fail2ban-server'")
    return salt_master_cmd(r"'salt \* state.single service.running name=fail2ban'")


#
#
#

@task
def sync_logs():
    stackname = 'elife-ci-2015-11-04'
    with stack_conn(stackname):
        map(sudo, [
            'mkdir -p /var/log/platformsh/',
            'ls -lahi /var/log/platformsh/',
            'rsync -avz -e ssh gzorsqexlzqta-master@ssh.eu.platform.sh:/tmp/log/ /var/log/platformsh/ --exclude "php.log" --inplace',
            'ls -lahi /var/log/platformsh/',            
        ])

#
#
#

def acme_enabled(url):
    "if given url can be hit and it looks like the acme hidden dir exists, return True."
    url = 'http://' + url + "/.well-known/acme-challenge/" # ll: http://lax.elifesciences.org/.well-known/acme-challenge
    try:
        resp = requests.head(url, allow_redirects=False)
        if 'crm.elifesciences' in url:
            return resp.status_code == 404 # apache behaves differently to nginx
        return resp.status_code == 403 # forbidden rather than not found.
    except:
        # couldn't connect for whatever reason
        return False

@task
@requires_aws_stack
@echo_output
@osissue("*very* useful task. improve with documentation.")
def fetch_cert(stackname):
    try:    
        # replicates some logic in builder core
        pname = core.project_name_from_stackname(stackname)
        all_project_data = project.project_data(pname)
        project_data = all_project_data[pname]

        assert project_data.has_key('subdomain'), "project subdomain not found. quitting"

        instance_id = stackname[len(pname + "-"):]
        is_prod = instance_id in ['master', 'production']

        # we still have some instances that are the production/master
        # instances but don't adhere to the naming yet.
        old_prods = [
            'elife-ci-2015-11-04',
            'elife-jira-2015-06-02'
        ]
        if not is_prod and stackname in old_prods:
            is_prod = True

        domain_names = ["%s.%s.elifesciences.org" % (instance_id, project_data['subdomain'])]
        if is_prod:
            project_hostname = "%s.elifesciences.org" % project_data['subdomain']
            if acme_enabled(project_hostname):
                domain_names.append(project_hostname)
            else:
                print '* project hostname (%s) doesnt appear to have letsencrypt enabled, ignore' % project_hostname

        print '\nthese hosts will be targeted:'
        print '* ' + '\n* '.join(domain_names)

        #pillar_data = cfngen.salt_pillar_data(config.PILLAR_DIR)
        #server = {
        #    'staging': pillar_data['sys']['webserver']['acme_staging_server'],
        #    'live': pillar_data['sys']['webserver']['acme_server'],
        #}
        server = {
            'staging': "https://acme-staging.api.letsencrypt.org/directory",
            'live': "https://acme-v01.api.letsencrypt.org/directory",
        }

        certtype = utils._pick("certificate type", ['staging', 'live'])

        cmds = [
            "cd /opt/letsencrypt/",
            "./fetch-ssl-certs.sh -d %s --server %s" % (" -d ".join(domain_names), server[certtype]),
            "sudo service nginx reload",
        ]

        print
        print 'the following commands will be run:'
        print ' * ' + '\n * '.join(cmds)
        print

        if raw_input('enter to continue, ctrl-c to quit') == '':
            with stack_conn(stackname):
                return run(" && ".join(cmds))

    except AssertionError, ex:
        print
        print "* " + str(ex)
        print
        exit(1)
