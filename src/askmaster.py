"""Questions we ask Master about our minions.

Requires access to the master server."""

from buildercore import core
from fabric.api import sudo
from buildercore.core import stack_conn
import utils

def salt_master_cmd(cmd, module='cmd.run', minions=r'\*'):
    "runs the given command on all aws instances. given command must escape double quotes"
    with stack_conn(core.find_master(utils.find_region())):
        sudo("salt %(minions)s %(module)s %(cmd)s --timeout=30" % locals())

def fail2ban_running():
    return salt_master_cmd(module="state.single", cmd="service.running name=fail2ban")

def installed_linux_kernel():
    "prints the list of linux kernels installed (but not necessarily running)"
    # ii  linux-image-4.15.0-1019-aws          4.15.0-1019.19                             amd64        Linux kernel image for version 4.15.0 on 64 bit x86 SMP
    # ii  linux-image-aws                      4.15.0.1019.19                             amd64        Linux kernel image for Amazon Web Services (AWS) systems.
    return salt_master_cmd("'dpkg -l | grep -i linux-image | grep -i ii'")

def linux_distro():
    "returns the version of the OS"
    # 'Description:    Ubuntu 18.04.1 LTS'
    return salt_master_cmd("'lsb_release -d'")

def update_kernel():
    cmd = "'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install linux-image-aws -y'"
    # 16.04+ minions only
    minion_set = [
        'G@osrelease:16.04',
        'G@osrelease:18.04',
    ]
    [salt_master_cmd(cmd, minions="--compound '%s'" % m) for m in minion_set]
