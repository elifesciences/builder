#!/bin/bash
# runs as ROOT on ALL AWS MINIONS directly after stack creation and before AMI 
# creation

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

if command -v salt-minion > /dev/null; then
    # salt is installed, probably using an AMI or creating an AMI
    # https://docs.saltstack.com/en/latest/ref/modules/all/salt.modules.saltutil.html#salt.modules.saltutil.clear_cache
    service salt-minion stop
fi

# remove leftover files from AMIs
rm -rf \
    /etc/cfn-info.json \
    /etc/salt/pki/minion/minion_master.pub \
    /etc/salt/minion \
    /root/.ssh/* \
    /etc/certificates/* \
    /root/events.log \
    /var/cache/salt/minion
