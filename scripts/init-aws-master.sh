#!/bin/bash
# AWS MASTER MINIONS ONLY
# this script is uploaded to master servers and called with the required params
# AFTER bootstrap.sh has been called. It performs a few further steps required 
# to configure a salt master on AWS prior to calling `highstate`

set -e # everything must succeed

stackname=$1 # who am I? ll: master-server--2016-01-01
pillar_repo=$2 # what secrets do I know?

echo "bootstrapping master-minion $stackname"

# no idea what creates this file or why it hangs around
# remove it if we find it so there is no ambiguity
rm -f /etc/salt/minion_id

if [ ! -f "/etc/salt/pki/master/minions/$stackname" ]; then
    # master hasn't accepted it's own key yet
    if [ ! -f /etc/salt/pki/minion/minion.pub ]; then
        # master hasn't generated it's own keys yet!
        echo "no minion key for master detected, restarting salt-master"
        service salt-master restart
    fi    
    mkdir -p /etc/salt/pki/master/minions/
    cp /etc/salt/pki/minion/minion.pub /etc/salt/pki/master/minions/$stackname
fi

# the minion properties are set in the `bootstrap.update_environment` function

# set the master properties

# no need to clone the elife-builder on the master
# BUT! we do need the organisation's secret pillar data. 
# this value is in the 'defaults' section of the project data and can be 
# overriden on a per-master basis.

# clone private repo (whatever it's name is) into /opt/builder-private/
# TODO: REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-private ]; then
    cd /opt
    git clone $pillar_repo builder-private
else
    cd /opt/builder-private
    git reset --hard
    git pull
fi

cd /srv
ln -sf /opt/builder-private/pillar/
ln -sf /opt/builder-private/salt/

# replace the master config, if it exists, with the builder-private copy
cp /opt/builder-private/etc-salt-master /etc/salt/master
# set the ip address
ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')
sed -i "s/<<ip-address>>/$ipaddr/g" /etc/salt/master

service salt-master restart
