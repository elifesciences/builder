#!/bin/bash
# AWS and VAGRANT *MASTER AND MINIONS*
# copied into the virtual machine and executed. DO NOT run on your host machine.

# significant parts taken from
# https://github.com/mitchellh/vagrant/issues/5973#issuecomment-126082024

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

echo "-----------------------------"

version=$1
stackname=$2
install_master=$3
master_ipaddr=$4

echo "salt version: $version"

# minion config

# ensures the SSH_AUTH_SOCK envvar is retained when we sudo to root
# this allows the root user to talk to private git repos
sudo sh -c "echo 'Defaults>root env_keep+=SSH_AUTH_SOCK' > /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod 440 /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod -R 777 /tmp"

if ! (salt-minion --version | grep $version); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # -P  Allow pip based installations.
    # -F  Allow copied files to overwrite existing(config, init.d, etc)
    # -c  Temporary configuration directory
    # -M  Also install master
    # https://github.com/saltstack/salt-bootstrap/blob/develop/bootstrap-salt.sh
    sudo sh salt_bootstrap.sh -P -F -c /tmp stable $version
else
    echo "Skipping minion bootstrap, found: $(salt-minion --version)"
fi

# master config

if [ "$install_master" == "true" ]; then
    # salt is not installed or the version installed is old
    if ! (type salt-master && salt-master --version | grep $version); then
        # master not installed
        sudo sh salt_bootstrap.sh -P -F -M -c /tmp stable $version
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi

# reset the minion config

if [ -d /vagrant ]; then
    # we're using Vagrant
    # ignore IP given and use the one we can detect
    master_ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')
    sudo ln -sf /project/salt /srv/salt
    sudo ln -sf /project/salt/pillar /srv/pillar
    # if master-server, these links will be overwritten
fi

# this file shouldn't exist but it does. leftover from installing salt? nfi.
sudo rm -f /etc/salt/minion_id
echo "
master: $master_ipaddr
id: $stackname
log_level: info" | sudo tee /etc/salt/minion

sudo service salt-minion restart
