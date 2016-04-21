#!/bin/bash
# copied into the virtual machine and executed. DO NOT run on your host machine.

# stolen from
# https://github.com/mitchellh/vagrant/issues/5973#issuecomment-126082024

set -e
start_seconds="$(date +%s)"
version=$1

if [ -n "$SALT_VERSION" ]; then
    #echo "overriden salt version found:" $SALT_VERSION
    version=$SALT_VERSION
fi
echo "salt version: " $version

# ensures the SSH_AUTH_SOCK envvar is retained when we sudo to root
# this allows the root user to talk to private git repos
sudo sh -c "echo 'Defaults>root env_keep+=SSH_AUTH_SOCK' > /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod 440 /etc/sudoers.d/00-ssh-auth-sock-root && \
            chmod -R 777 /tmp"

if ! (salt-call --version | grep $version); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # accepts an envvar of SALT_VERSION. explicit parameter override envvar
    version=$SALT_VERSION
    if [ ! -z "$1" ]; then version=$1; fi

    # -P  Allow pip based installations.
    # -F  Allow copied files to overwrite existing(config, init.d, etc)
    # -c Temporary configuration directory
    # https://github.com/saltstack/salt-bootstrap/blob/develop/bootstrap-salt.sh
    sudo sh salt_bootstrap.sh -P -F -c /tmp stable $version
else
    echo "Skipping bootstrap, found: $(salt-call --version)"
fi

echo "-----------------------------"

end_seconds="$(date +%s)"
echo "Salt installation complete in "$(expr $end_seconds - $start_seconds)" seconds"
