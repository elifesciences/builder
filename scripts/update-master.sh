#!/bin/bash
# executed as ROOT on AWS and Vagrant
# called regularly to install/reset project formulas, update the master config

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

cd /opt/builder-private
git reset --hard
git checkout master
git pull --rebase

cd /opt/builder-configuration
git reset --hard
git checkout master
git pull --rebase

# ... then clone/pull all formula repos and update master config
cd /opt/formulas
for formula in *; do
    (
        cd "$formula"
        git reset --hard
        git clean -d --force
        current_branch=$(git rev-parse --abbrev-ref HEAD)
        if [ "$current_branch" != 'HEAD' ]; then
            git pull --rebase
        else
            echo "Repository on a detached HEAD, not pulling any branch"
        fi
    )
done

# BUG: when /var/run/salt-master.pid not present it causes script to exit
master_pid=$(test -e /var/run/salt-master.pid && cat /var/run/salt-master.pid)
if [ "$master_pid" != "" ]; then
    systemctl stop salt-master 2> /dev/null || true
    # wait for salt-master to exit
    timeout 2 tail --pid="$master_pid" -f /dev/null || true
fi

# we were patient and polite, but if it's still running we kill it hard
killall -9 salt-master || true

systemctl start salt-master 2> /dev/null

