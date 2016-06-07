#!/bin/bash
# VAGRANT AND AWS bootstrap.sh
# copied into the virtual machine and executed. DO NOT run on your host machine.

# stolen from
# https://github.com/mitchellh/vagrant/issues/5973#issuecomment-126082024

set -e

echo "-----------------------------"

version=$1
install_master=$2

if [ -n "$SALT_VERSION" ]; then
    #echo "overriden salt version found:" $SALT_VERSION
    version=$SALT_VERSION
fi
echo "salt version: " $version

# minion config

# ensures the SSH_AUTH_SOCK envvar is retained when we sudo to root
# this allows the root user to talk to private git repos
sudo sh -c "echo 'Defaults>root env_keep+=SSH_AUTH_SOCK' > /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod 440 /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod -R 777 /tmp"

if ! (salt-minion --version | grep $version); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # accepts an envvar of SALT_VERSION. explicit parameter override envvar
    version=$SALT_VERSION
    if [ ! -z "$1" ]; then version=$1; fi

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

if [ -n "$install_master" ]; then
    # salt is not installed or the version installed is old
    if ! (type salt-master && salt-master --version | grep $version); then
        # master not installed
        sudo sh salt_bootstrap.sh -P -F -M -c /tmp stable $version
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi

# ensure this minion has a key
if [ ! -f /etc/salt/pki/minion/minion.pub ]; then
    echo "no minion pub key found, generating"
    salt-key --gen-keys /etc/salt/pki/minion/minion
fi

# ensure the gitfs backend deps are installed
# this is only needed on the master or masterless (vagrant) minions
#sudo apt-get install python-git -y
sudo apt-get install python-setuptools python-dev libgit2-dev libffi-dev python-git -y
