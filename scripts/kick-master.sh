#!/bin/bash
# only use this as a last resort

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

service salt-minion stop
service salt-master stop
sudo killall salt-call   || true

sleep 2

ps aux | grep -i salt

sudo killall salt-minion || true
sudo killall salt-master || true

service salt-master start
service salt-minion start

# some health checking
# https://docs.saltstack.com/en/latest/ref/modules/all/salt.modules.saltutil.html#salt.modules.saltutil.sync_all
salt-call saltutil.sync_all -l trace
if (! salt-call sys.list_modules | grep elife); then
    echo "couldn't find the 'elife' module. master server is in a bad state"
    exit 1
fi
