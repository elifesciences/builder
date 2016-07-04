#!/bin/bash
# * AWS MASTER MINIONS ONLY
# * run as ROOT
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

if [ ! -f /root/.ssh/id_rsa.pub ]; then
    # generate/overwrite the *pubkey*
    # -y read pemkey, print pubkey to stdout
    # -f path to pemkey
    ssh-keygen -y -f /root/.ssh/id_rsa > /root/.ssh/id_rsa.pub
    chmod 600 /root/.ssh/id_rsa # read/write for owner
    chmod 644 /root/.ssh/id_rsa.pub # read/write for owner, world readable
fi

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

# the minion properties are set in the `bootstrap.update_stack` function

# set the master properties

# we do need the organisation's secret pillar data
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

# this is one way of configuring the master ...
#cd /srv
#ln -sf /opt/builder-private/pillar/
#ln -sf /opt/builder-private/salt/

# ... another approach is using gitfs remotes
# https://docs.saltstack.com/en/latest/topics/tutorials/gitfs.html

# replace the master config, if it exists, with the builder-private copy
cp /opt/builder-private/etc-salt-master /etc/salt/master

# update the salt config with the ip address of the machine
ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')
sed -i "s/<<private-ip-address>>/$ipaddr/g" /etc/salt/master

# this needs more work.
# restarting the salt-master appears to orphan lock files that prevents
# remote pillars from being updated.
# also seems to be having problems with multiple salt-master processes running.
# this might be contributing to the lock problem.

# clear all lock files
# this command doesn't require salt-master to be running
salt-run cache.clear_git_lock git_pillar type=update || true

# only in rare cases where there are multiple salt-master processes running
#sudo('killall salt-master -s 15')

service salt-master restart
