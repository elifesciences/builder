"""Questions we ask Master about our minions.

Requires access to the master server."""

import utils
from buildercore import core
from buildercore.command import remote_sudo
from buildercore.core import stack_conn


def salt_master_cmd(cmd, module='cmd.run', minions=r'\*'):
    """runs the given command on all connected minions.
    given command must escape double quotes.

    example `minions` strings:

    '*'                 # all minions
    'lax--*'            # all 'lax' minions
    'lax--prod--*'      # all 'lax--prod' minions
    '*--prod--*'        # all 'prod' minions
    '*--prod--* or *--continuumtest--*' # all 'prod' and 'continuumtest' minions
    "--compound 'G@osrelease:18.04'" # 18.04+ minions only

    see: https://docs.saltproject.io/en/latest/topics/targeting/"""

    with stack_conn(core.find_master(utils.find_region())):
        remote_sudo("salt %(minions)s %(module)s %(cmd)s --timeout=30" % locals())

def fail2ban_running():
    """starts fail2ban on all machines if it's not already running.
    fail2ban monitors ssh access and bars entry after repeated failed attempts."""
    return salt_master_cmd(module="state.single", cmd="service.running name=fail2ban")

def installed_linux_kernel():
    """prints the list of linux kernels installed.
    note: a kernel may be installed but not running (system needs restart)."""
    # ii  linux-image-4.15.0-1019-aws          4.15.0-1019.19                             amd64        Linux kernel image for version 4.15.0 on 64 bit x86 SMP
    # ii  linux-image-aws                      4.15.0.1019.19                             amd64        Linux kernel image for Amazon Web Services (AWS) systems.
    return salt_master_cmd("'dpkg -l | grep -i linux-image | grep -i ii'")

def installed_salt_version():
    """returns the version of Salt in use.
    good for testing all minions have been upgraded.
    looks like: 'salt-call 2019.2.4 (Fluorine)'"""
    return salt_master_cmd("'salt-call --version'")

def linux_distro():
    """returns the version of the OS
    looks like: 'Description:    Ubuntu 18.04.1 LTS'"""
    return salt_master_cmd("'lsb_release -d'")
