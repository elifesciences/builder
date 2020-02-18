#!/bin/bash
set -e # everything must pass
set -u # no unbound variables

# todo: make this a --dry-run parameter or similar
just_test=false

if $just_test; then
    sudo salt-call --force-color state.highstate -l info test=True --retcode-passthrough
else
    echo "Executing salt highstate (provisioning)"
    log_file=/var/log/salt/salt-highstate-$(date "+%Y-%m-%dT%H:%M:%S").log
    set -o pipefail
    sudo salt-call --force-color state.highstate -l info --retcode-passthrough | tee "$log_file" || {
        status=$?
        echo "Error provisioning, state.highstate returned: ${status}"
        logger "Salt highstate failure: $log_file on $(hostname)"
        exit $status
    }
fi
