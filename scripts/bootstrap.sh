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

# ensures the SSH_AUTH_SOCK envvar is retained when we sudo to root
# this allows the root user to talk to private git repos
echo 'Defaults>root env_keep+=SSH_AUTH_SOCK' > /etc/sudoers.d/00-ssh-auth-sock-root
chmod 440 /etc/sudoers.d/00-ssh-auth-sock-root
chmod -R 777 /tmp


installing=false
upgrading=false
if [ ! -e /root/events.log ]; then
    # we're installing for the first time if: we can't find an event.log file.
    # this file is deleted upon stack creation and populated after successful 
    # salt installation
    installing=true
else
    if ! (salt-minion --version | grep "$version"); then
        upgrading=true
    fi
fi


# install git
if ! dpkg -l git &> /dev/null; then
    apt-get install git -y
fi


# salt-minion
if ($installing || $upgrading); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # -P  Allow pip based installations.
    # -F  Allow copied files to overwrite existing(config, init.d, etc)
    # -c  Temporary configuration directory
    # -M  Also install master
    # https://github.com/saltstack/salt-bootstrap/blob/develop/bootstrap-salt.sh
    sh salt_bootstrap.sh -P -F -c /tmp stable "$version"
else
    echo "Skipping minion bootstrap, found: $(salt-minion --version)"
fi


# salt-master
if [ "$install_master" = "true" ]; then
    # salt is not installed or the version installed is old
    if ! (command -v salt-master > /dev/null && salt-master --version | grep "$version"); then
        # master not installed
        sh salt_bootstrap.sh -P -F -M -c /tmp stable "$version"
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi


# record some basic provisioning info after the above successfully completes
if $installing; then echo "$(date -I) -- installed $version" >> /root/events.log; fi
if $upgrading; then echo "$(date -I) -- upgraded to $version" >> /root/events.log; fi


# reset the minion config and
# put minion id in dedicated file else salt keeps recreating file
echo "
master: $master_ipaddr
log_level: info" > /etc/salt/minion

echo "$stackname" > /etc/salt/minion_id
if [ -d /vagrant ]; then
    # we're using Vagrant    

    # ignore IP parameter and use the one we can detect
    master_ipaddr=$(ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://')

    # link up the project formula mounted at /project
    # NOTE: these links will be overwritten if this a master-server instance
    ln -sfn /project/salt /srv/salt
    ln -sfn /project/salt/pillar /srv/pillar
    ln -sfn /vagrant/custom-vagrant /srv/custom
    
    # by default the project's top.sls is disabled by file naming. hook that up here
    cd /srv/salt/ && ln -sf example.top top.sls
    
    # install the builder base formula 
    if [ ! -d /vagrant/cloned-projects/builder-base-formula/.git ]; then
        git clone https://github.com/elifesciences/builder-base-formula \
            /vagrant/cloned-projects/builder-base-formula
    fi
    
    # overwrite the general purpose /etc/salt/minion file created above with 
    # this more complex one for dev environments only
    cp /vagrant/scripts/salt/minion /etc/salt/minion
fi


#  service restart necessary as we've changed the minion's configuration
service salt-minion restart


# generate a key for the root user
# in AWS this is uploaded to the server and moved into place prior to calling 
# this script. in Vagrant it must be created.
if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -f /root/.ssh/id_rsa -N ''
fi
touch /root/.ssh/known_hosts


# ensure salt can talk to github without host verification failures
ssh-keygen -R github.com # removes any existing keys
# append this to the global known hosts file
echo "github.com,192.30.252.128 ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==" >> /etc/ssh/ssh_known_hosts

