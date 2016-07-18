#!/bin/bash
# called regularly to install/reset project formulas, update the master config
# majority of logic lives in ./builder/src/remote_master.py

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

cd /opt/builder
if [ ! -d /vagrant ]; then
    git reset --hard
    git pull --rebase
fi

# install/update any python requirements
/bin/bash .activate-venv.sh

# this  clones/pulls all repos and updates the master config
BLDR_ROLE=master ./bldr remote_master.refresh

service salt-master stop || true

sleep 2

sudo killall salt-master || true

service salt-master start
