#!/bin/bash
set -e # everything must pass
set -u # no unbound variables

echo "Executing salt highstate (provisioning)"
sudo salt-call state.highstate --retcode-passthrough || {
    status=$?
    echo "Error provisioning, state.highstate returned: ${status}"
}
