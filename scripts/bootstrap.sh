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
echo 'Defaults>root env_keep+=SSH_AUTH_SOCK' > /etc/sudoers.d/00-ssh-auth-sock-root
chmod 440 /etc/sudoers.d/00-ssh-auth-sock-root
chmod -R 777 /tmp

if ! (salt-minion --version | grep $version); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # -P  Allow pip based installations.
    # -F  Allow copied files to overwrite existing(config, init.d, etc)
    # -c  Temporary configuration directory
    # -M  Also install master
    # https://github.com/saltstack/salt-bootstrap/blob/develop/bootstrap-salt.sh
    sh salt_bootstrap.sh -P -F -c /tmp stable $version
else
    echo "Skipping minion bootstrap, found: $(salt-minion --version)"
fi

# master config

if [ "$install_master" == "true" ]; then
    # salt is not installed or the version installed is old
    if ! (type salt-master && salt-master --version | grep $version); then
        # master not installed
        sh salt_bootstrap.sh -P -F -M -c /tmp stable $version
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi

# reset the minion config

if [ -d /vagrant ]; then
    # we're using Vagrant
    
    # ignore IP parameter and use the one we can detect
    master_ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')
    
    # link up the project formula mounted at /project
    ln -sf /project/salt /srv/salt
    ln -sf /project/salt/pillar /srv/pillar
    # if a master-server instance, these links will be overwritten
fi

# this file shouldn't exist but it does. leftover from installing salt? nfi.
rm -f /etc/salt/minion_id
echo "
master: $master_ipaddr
id: $stackname
log_level: info" > /etc/salt/minion

# we've changed the minion's configuration, service restart necessary
service salt-minion restart

# generate a key for the master server. 
# in AWS this is uploaded to the server and moved into place prior to calling this script
# in Vagrant it must be created
if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -f /root/.ssh/id_rsa -N ''
fi
touch /root/.ssh/known_hosts

# ensure salt can talk to github without host verification failures
ssh-keygen -R github.com # removes any existing keys
# append this to the global known hosts file
echo "github.com,192.30.252.128 ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==" >> /etc/ssh/ssh_known_hosts

