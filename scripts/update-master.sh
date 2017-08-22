#!/bin/bash
# executed as ROOT on AWS and Vagrant
# called regularly to install/reset project formulas, update the master config
# python logic lives in ./builder/src/remote_master.py

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

cd /opt/builder-private
if [ ! -d /vagrant ]; then
    # NOT vagrant. if this were vagrant, any dev changes would be reset
    git reset --hard
    git pull --rebase
fi


cd /opt/builder/
if [ ! -d /vagrant ]; then
    # NOT vagrant. if this were vagrant, any dev changes would be reset
    git reset --hard
    git pull --rebase
fi

# hook!
# custom builder settings.yml for the master server
if [ -e /opt/builder-private/master-server-settings.yml ]; then
    rm -f settings.yml
    ln -s /opt/builder-private/master-server-settings.yml settings.yml
fi

# install/update any python requirements
/bin/bash .activate-venv.sh

# replace the master config, if it exists, with the builder-private copy ...
cp /opt/builder-private/etc-salt-master /etc/salt/master

env
# ... then clone/pull all formula repos and update master config
cd /opt/formulas
for formula in `ls`; do
    cd $formula
    git reset --hard
    git clean -d --force
    git pull --rebase
    cd ..
done
cd /opt/builder
BLDR_ROLE=master ./bldr remote_master.refresh

service salt-master stop || true

sleep 2

sudo killall -9 salt-master || true

service salt-master start
