#!/bin/bash
# runs as ROOT before AMI creation
# creation

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

if command -v salt-minion > /dev/null; then
    # salt is installed
    systemctl stop salt-minion 2> /dev/null || service salt-minion stop
fi

# remove credentials and stack-specific files
rm -rf \
    /etc/cfn-info.json \
    /etc/salt/pki/minion/* \
    /etc/salt/minion \
    /root/.ssh/* \
    /home/elife/.ssh/* \
    /home/ubuntu/.ssh/id_rsa* \
    /etc/certificates/* \
    /root/events.log \
    /var/cache/salt/minion \
    /etc/apt/sources.list.d/saltstack.list

# commit memory buffers to disk to avoid partly written files
# since AMIs are essentially snapshots of the root volume
sync
