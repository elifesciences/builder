"""Questions we ask Master about our minions.

Requires access to the master server."""

from buildercore import core
from fabric.api import sudo, task
from decorators import echo_output
from buildercore.core import stack_conn
import aws, utils
from buildercore.decorators import osissue
import string

@task
def salt_master_cmd(cmd, module='cmd.run', minions=r'\*'):
    "runs the given command on all aws instances. given command must escape double quotes"
    with stack_conn(core.find_master(aws.find_region())):
        return sudo("salt %(minions)s %(module)s %(cmd)s --timeout=2 --no-color " % locals())

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
    return salt_master_cmd("'dpkg -l | grep -i linux-image && uname -r'")

#
#
#

@task
def patched():
    output = str(installed_linux()).splitlines()
    #output = open('src/foo.txt', 'r').readlines()

    def rowfn(row):
        # parses output of dpkg -l
        row = filter(None, row.strip().split('  '))
        row = map(string.strip, row)
        if len(row) > 1:
            if row[0] == 'rc':
                return utils.EXCLUDE_ME
            if row[1].endswith('-virtual'):
                return utils.EXCLUDE_ME
        return row

    groups = utils.parse_salt_master_output(output, rowfn)

    fully_patched = [
        '3.13.0-139-generic', '3.13.0-139.188',
        '4.4.0-1048-aws', '4.4.0.1048.50'
    ]

    csvrows = [('instance', 'instance-id', 'running', 'installed', 'running latest', 'needs update', 'needs reboot')]
    for gname, gitems in groups.items():
        if not gitems:
            continue

        running_patch = gitems[-1][0].strip()

        installed_patches = sorted(gitems[:-1], key=lambda row: row[2])
        greatest_patch = installed_patches[-1][2] # ignores trailing 'virtual' patch

        running_latest = running_patch in fully_patched # the patch is installed and running
        needs_update = not running_latest and greatest_patch not in fully_patched # the patch hasn't been downloaded
        needs_reboot = not running_latest or needs_update # the patch is installed but isn't running

        iid = gname.split('--')[1]
        row = (gname, iid, running_patch, greatest_patch, running_latest, needs_update, needs_reboot)
        csvrows.append(row)

    utils.writecsv('patch-report.csv', csvrows)
