#!/bin/bash
set -e # everything must pass

arg1=$1 # --dry-run

dry_run=false
if [ "$arg1" = "--dry-run" ]; then
    dry_run=true
fi

# coloured output enabled by default. disabled in CI environments.
force_color="--force-color"
if [ -n "$SALT_NO_COLOR" ]; then
    force_color=""
fi

if $dry_run; then
    echo "Executing salt highstate (testing)"
    sudo salt-call "$force_color" state.highstate -l info test=True --retcode-passthrough
else
    echo "Executing salt highstate"
    log_file=/var/log/salt/salt-highstate-$(date "+%Y-%m-%dT%H:%M:%S").log
    set -o pipefail
    sudo salt-call "$force_color" state.highstate -l info --retcode-passthrough | tee "$log_file" || {
        status=$?
        echo "Error provisioning, state.highstate returned: ${status}"
        logger "Salt highstate failure: $log_file on $(hostname)"
        exit $status
    }
fi
