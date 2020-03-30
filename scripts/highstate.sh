#!/bin/bash
set -e # everything must pass
set -u # no unbound variables

arg1=$1 # --dry-run

dry_run=false
if [ "$arg1" = "--dry-run" ]; then
    dry_run=true
fi

if $dry_run; then
    echo "Executing salt highstate (testing)"
    sudo salt-call --force-color state.highstate -l info test=True --retcode-passthrough
else
    echo "Executing salt highstate"
    log_file=/var/log/salt/salt-highstate-$(date "+%Y-%m-%dT%H:%M:%S").log
    set -o pipefail
    sudo salt-call --force-color state.highstate -l info --retcode-passthrough | tee "$log_file" || {
        status=$?
        echo "Error provisioning, state.highstate returned: ${status}"
        logger "Salt highstate failure: $log_file on $(hostname)"
        exit $status
    }
fi
