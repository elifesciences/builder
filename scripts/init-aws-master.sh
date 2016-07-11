#!/bin/bash
# * AWS MASTER MINIONS ONLY
# * run as ROOT
# this script is uploaded to master servers and called with the required params
# AFTER bootstrap.sh has been called. It performs a few further steps required 
# to configure a salt master on AWS prior to calling `highstate`

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

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


# install/update builder
# the master will need to fetch a list of projects and create symlinks to 
# formulas within /srv/salt and /srv/pillar

# install builder dependencies for Ubuntu
apt-get install python-dev python-pip -y
pip install virtualenv

# install builder
#rm -rf /opt/builder
if [ ! -d /opt/builder ]; then
    cd /opt
    git clone https://github.com/elifesciences/builder
    cd builder
    touch .no-vagrant-s3auth.flag
    touch .no-install-basebox.flag
    touch .no-delete-venv.flag

    # hook!
    # if you want your master server to look at your own projects, or multiple
    # project files, or ...
    if [ -e /opt/builder-private/master-server-settings.yml ]; then
        rm settings.yml
        ln -s /opt/builder-private/master-server-settings.yml settings.yml
    fi

else
    cd /opt/builder
    #git reset --hard
    git pull
fi


# some vagrant wrangling for convenient development
if [ -d /vagrant ]; then
    # we're inside Vagrant!
    if [ -d /opt/builder/src/ ]; then
        # the src directory is still a directory.
        # remove the installed builder's src directory
        rm -rf /opt/builder/src
        ln -s /vagrant/src src
    fi
fi

# install the virtualenv but don't die if some userland deps don't exist
./update.sh --exclude virtualbox vagrant

# replace the master config, if it exists, with the builder-private copy
cp /opt/builder-private/etc-salt-master /etc/salt/master

# replace the master config, if it exists, with the builder-private copy
cp /opt/builder-private/etc-salt-master /etc/salt/master

# update the salt config with the ip address of the machine
ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')
sed -i "s/<<private-ip-address>>/$ipaddr/g" /etc/salt/master

# this is one way of configuring the master ...
cd /srv
ln -sf /opt/builder-private/pillar/
ln -sf /opt/builder-private/salt/

# ... another approach is using gitfs remotes
# https://docs.saltstack.com/en/latest/topics/tutorials/gitfs.html

# we've found gitfs to be too magical and too unreliable. we prefer to:
# * inspect the current state by looking at the filesystem
# * avoid the problem with git lock files not being cleared

# this runs the 'install_update_all_projects' task in the ./src/remote_master.py
# module in the builder project. it clones/pulls all repos and creates symlinks.
cd /opt/builder/
BLDR_ROLE=master ./bldr remote_master.install_update_all_projects

service salt-master restart
