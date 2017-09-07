#!/bin/bash
# executed as ROOT on AWS and Vagrant
# called regularly to install/reset project formulas, update the master config

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

cd /opt/builder-private
git reset --hard
git pull --rebase

# ... then clone/pull all formula repos and update master config
cd /opt/formulas
for formula in *; do
    (
        cd "$formula"
        git reset --hard
        git clean -d --force
        git pull --rebase
    )
done

master_pid=$(test -e /var/run/salt-master.pid && cat /var/run/salt-master.pid)
if [ "$master_pid" != "" ]; then
    service salt-master stop || true
    # wait for salt-master to exit
    timeout 2 tail --pid="$master_pid" -f /dev/null || true
fi

sudo killall -9 salt-master || true

service salt-master start
