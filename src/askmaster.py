"""Questions we ask Master about our minions.

Requires access to the master server."""

from buildercore import core
from fabric.api import sudo, task
from decorators import echo_output
from buildercore.core import stack_conn
from buildercore.decorators import osissue
import utils

def salt_master_cmd(cmd, module='cmd.run', minions=r'\*'):
    "runs the given command on all aws instances. given command must escape double quotes"
    with stack_conn(core.find_master(utils.find_region())):
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

@task
def fail2ban_running():
    # return salt_master_cmd("'ps aux | grep fail2ban-server'")
    return salt_master_cmd(r"'salt \* state.single service.running name=fail2ban'")

@task
def installed_linux():
    return salt_master_cmd("'dpkg -l | grep -i linux-image'")
