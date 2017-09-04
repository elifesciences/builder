#!/bin/bash
# executed as ROOT on AWS and Vagrant
# called regularly to install/reset project formulas, update the master config

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

cd /opt/builder-private
if [ ! -d /vagrant ]; then
    # NOT vagrant. if this were vagrant, any dev changes would be reset
    git reset --hard
    git pull --rebase
fi

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

service salt-master stop || true

sleep 2

sudo killall -9 salt-master || true

service salt-master start
