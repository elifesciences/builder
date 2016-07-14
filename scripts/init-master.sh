#!/bin/bash
# * AWS and VAGRANT *MASTER* MINIONS ONLY
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

# generate a key for the master server. 
# in AWS this is uploaded to the server and moved into place prior to calling this script
# in Vagrant it must be created
if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -f /root/.ssh/id_rsa -N ''
fi


if [ -d /vagrant ]; then
    # ensure salt can talk to github without host verification failures
    #ssh-keygen -R github.com # removes any matching keys
    sudo cp /vagrant/scripts/etc-known_hosts /etc/ssh/ssh_known_hosts
fi


# generate/overwrite the *pubkey*
if [ ! -f /root/.ssh/id_rsa.pub ]; then    
    # -y read pemkey, print pubkey to stdout
    # -f path to pemkey
    ssh-keygen -y -f /root/.ssh/id_rsa > /root/.ssh/id_rsa.pub
    chmod 600 /root/.ssh/id_rsa # read/write for owner
    chmod 644 /root/.ssh/id_rsa.pub # read/write for owner, world readable
fi


# test if master hasn't accepted it's own key yet
if [ ! -f "/etc/salt/pki/master/minions/$stackname" ]; then
    if [ ! -f /etc/salt/pki/minion/minion.pub ]; then
        # master hasn't generated it's own keys yet!
        echo "no minion key for master detected, restarting salt-master"
        service salt-master restart
        service salt-minion restart
    fi
    # minion keys for master should exist at this point
    mkdir -p /etc/salt/pki/master/minions/
    cp /etc/salt/pki/minion/minion.pub /etc/salt/pki/master/minions/$stackname
fi


# clone the private repo (whatever it's name is) into /opt/builder-private/
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
# the master server will need to install project formulas. 

# install builder dependencies for Ubuntu
apt-get install python-dev python-pip -y
pip install virtualenv

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
    git reset --hard
    git clean -d --force
    git pull --rebase
fi

# install the virtualenv but don't die if some userland deps don't exist
./update.sh --exclude virtualbox vagrant


# some vagrant wrangling for convenient development
if [ -d /vagrant ]; then
    # we're inside Vagrant!

    # if there is a directory called builder-private, then use it's contents 
    if [ -d /vagrant/builder-private ]; then
        rsync -av /vagrant/builder-private/ /opt/builder-private/
    fi
    rsync -av /vagrant/src/ /opt/builder/src/
    rsync -av /vagrant/scripts/ /opt/builder/scripts/
    rsync -av /vagrant/projects/ /opt/builder/projects/
fi


# replace the master config, if it exists, with the builder-private copy
cp /opt/builder-private/etc-salt-master /etc/salt/master

cd /srv
ln -sf /opt/builder-private/pillar
ln -sf /opt/builder-private/salt

echo "master server configured"

