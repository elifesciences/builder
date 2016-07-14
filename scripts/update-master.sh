#!/bin/bash
# run this regularly to install/reset project formulas, update the master config
# majority of logic lives in ./builder/src/remote_master.py

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

# this  clones/pulls all repos and updates the master config
cd /opt/builder/
BLDR_ROLE=master ./bldr remote_master.refresh

# kill any salt-thing that may be running
# why? encountering an issue where there are multiple salt-master processes
# running, or a salt-call process waiting on a response from a dead master
# it's such a hack.
sudo killall salt-call   || true
sudo killall salt-minion || true
sudo killall salt-master || true

sleep 1 # give them a moment to die

service salt-master restart
service salt-minion restart

# some health checking
# https://docs.saltstack.com/en/latest/ref/modules/all/salt.modules.saltutil.html#salt.modules.saltutil.sync_all
salt-call saltutil.sync_all -l trace
if (! salt-call sys.list_modules | grep elife); then
    echo "couldn't find the 'elife' module. master server is in a bad state"
    exit 1
fi
