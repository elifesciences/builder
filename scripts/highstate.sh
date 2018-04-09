#!/bin/bash
set -e # everything must pass
set -u # no unbound variables

# TODO? enabling this will kill any 'stuck' highstate calls
# killall salt-call

# ELPP-3448 temporary: allow switching back to an old master,
# which is the currently bugged behavior but it prevents
# master key pinning from blocking all builds of upgraded projects (that have been remastered to the new master)
sudo rm -f /etc/salt/pki/minion/minion_master.pub

echo "Executing salt highstate (provisioning)"
log_file=/var/log/salt/salt-highstate-$(date "+%Y-%m-%dT%H:%M:%S").log
set -o pipefail
sudo salt-call --force-color state.highstate -l info --retcode-passthrough | tee "$log_file" || {
    status=$?
    echo "Error provisioning, state.highstate returned: ${status}"
    logger "Salt highstate failure: $log_file on $(hostname)"
    exit $status
}
