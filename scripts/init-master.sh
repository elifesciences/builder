#!/bin/bash
# * AWS and VAGRANT *MASTER* MINIONS ONLY
# * run as ROOT
# this script is uploaded to master servers and called with the required params
# AFTER bootstrap.sh has been called. It performs a few further steps required 
# to configure a salt master on AWS prior to calling `highstate`

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

export DEBIAN_FRONTEND=noninteractive # no ncurses prompts

echo "-----------------------------"

stackname=$1 # who am I? "master-server--prod"
pillar_repo=$2 # what secrets do I know?
configuration_repo=$3 # what configuration do I know?
formulas=$4 # which formulas will I use?
formula_root="/opt/formulas"

echo "bootstrapping master-minion $stackname"

# generate/overwrite the *pubkey*
if [ ! -f /root/.ssh/id_rsa.pub ]; then    
    # -y read pemkey, print pubkey to stdout
    # -f path to pemkey
    ssh-keygen -y -f /root/.ssh/id_rsa > /root/.ssh/id_rsa.pub
    chmod 600 /root/.ssh/id_rsa # read/write for owner
    chmod 644 /root/.ssh/id_rsa.pub # read/write for owner, world readable
fi


# test if master hasn't accepted its own key yet
if [ ! -f "/etc/salt/pki/master/minions/$stackname" ]; then
    if [ ! -f /etc/salt/pki/minion/minion.pub ]; then
        # master hasn't generated it's own keys yet!
        echo "no minion key for master detected, restarting salt-master"
        systemctl restart salt-master 2> /dev/null
    fi
    # minion keys for master should exist at this point
    mkdir -p /etc/salt/pki/master/minions/
    # TODO: not sure why this is needed?
    # other nodes usually just start using the master without
    # their key manually configured
    #cp /etc/salt/pki/minion/minion.pub "/etc/salt/pki/master/minions/$stackname"
fi


# clone the private repo (whatever its name is) into /opt/builder-private/
# REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-private ]; then
    cd /opt
    git clone "$pillar_repo" builder-private || {
        set +xv
        pubkey=$(cat /root/.ssh/id_rsa.pub)
        echo "
----------

could not clone the 'builder-private' repository:
    $pillar_repo

add the following public key to the elife-master-builder Github user:

    $pubkey

which you can retrieve with:
    
    ./bldr download_file:$stackname,/root/.ssh/id_rsa.pub,/tmp,use_bootstrap_user=True

after the setup of the key, complete this process by running builder's 'update' command:

    ./bldr update:$stackname

This key will also be used to access any private formula you want the master-server to use.

The elife-master-builder Github user should already have access to these formulas.

----------"

        exit 1
    }
else
    cd /opt/builder-private
    git clean -d --force # in vagrant, destroys any uncommitted rsync'd files
    git reset --hard
    git checkout master
    git pull
fi
cp /opt/builder-private/etc-salt-master /etc/salt/master.template
if [ -d /vagrant ]; then
    cp /etc/salt/master.template /vagrant/etc-salt-master.template
fi

# clone builder-configuration in /opt/builder-configuration
if [ ! -d /opt/builder-configuration ]; then
    cd /opt
    git clone "$configuration_repo" builder-configuration --quiet
else
    cd /opt/builder-configuration
    git clean -d --force # in vagrant, destroys any uncommitted rsync'd files
    git reset --hard
    git checkout master
    git pull
fi


# clone all formulas
mkdir -p $formula_root
cd $formula_root
for formula_repo in $formulas
do
    pname=${formula_repo##*/} # "personalised-covers-formula"
    pname=${pname%-formula} # "personalised-covers"
    echo "Initializing $pname ($formula_repo)"
    if [ -d "$pname" ]; then
        (
            cd "$pname"
            git reset --hard
            git clean -d --force
            git pull --rebase
        )
    else
        git clone "$formula_repo" "$pname" --quiet
    fi
done

# some vagrant wrangling for convenient development
if [ -d /vagrant ]; then
    # we're inside Vagrant!
    # if there is a host directory called builder-private, then use it's contents 
    if [ -d /vagrant/builder-private ]; then
        rsync -av /vagrant/builder-private/ /opt/builder-private/
    fi
fi

# installed during bootstrap, the salt-minion is probably unhappy at this point. reboot it.
systemctl restart salt-minion 2> /dev/null

echo "master server configured"

