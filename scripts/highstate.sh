#!/bin/bash
# run as root
set -e

# lsh@2022-10-28: PATH copied from the /etc/sudoers 'secure_path' value.
# script would otherwise rely on caller's execution environment to succeed.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

arg1=$1 # --dry-run
arg2=$2 # --no-color

# a dry run will plan a highstate and emit a report but won't actually run.
dry_run=false
if [ "$arg1" = "--dry-run" ]; then
    dry_run=true
fi

# coloured output is enabled by default.
force_color="--force-color"
if [ "$arg2" = "--no-color" ]; then
    force_color=""
fi

# lsh@2022-10-12: temporary downgrade of a lib that salt installs during bootstrap.
# remove once salt fixes issue with importlib>=5.0.0
# - https://github.com/elifesciences/issues/issues/7782
# - https://github.com/python/importlib_metadata/issues/409
#pip3 install 'importlib_metadata==4.13.0'
# lsh@2023-05-01: downgraded again after new issue with importlib-metadata.
# - https://alfred.elifesciences.org/job/process/job/process-ec2-plugin-ami-update/105/console
#pip3 install 'importlib_metadata==4.12.0'
# lsh@2023-05-09: issue still not fixed, another downgrade to 4.6.4 seems to let me start the salt-minion without issue.
pip3 install 'importlib_metadata==4.6.4'

if $dry_run; then
    echo "Executing salt highstate (testing)"
    # shellcheck disable=SC2086
    salt-call $force_color state.highstate -l info test=True --retcode-passthrough
else
    echo "Executing salt highstate"
    log_file=/var/log/salt/salt-highstate-$(date "+%Y-%m-%dT%H:%M:%S").log
    set -o pipefail
    # shellcheck disable=SC2086
    salt-call $force_color state.highstate -l info --retcode-passthrough | tee "$log_file" || {
        status=$?

        # we can't guarantee '/etc/build-vars.json.b64', 'jq' or the 'build_vars' script exists when this script is run. 
        # It may be a vagrant machine or the first highstate.
        # However, we can test for the build vars and we can guarantee that base64 and python exist (see bootstrap.sh).
        # "elife-alfred--prod--1" or "prod--alfred.elifesciences.org"
        node_name=$( (test -f /etc/build-vars.json.b64 && base64 -d /etc/build-vars.json.b64 | python3 -c 'import json; import sys; print(json.loads(sys.stdin.read())["nodename"])') || hostname)

        echo "Error provisioning, state.highstate returned: ${status}"
        logger "Salt highstate failure: $log_file on $node_name"
        exit $status
    }
fi
