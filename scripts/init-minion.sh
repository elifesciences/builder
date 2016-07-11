#!/bin/bash
# VAGRANT ONLY
# copied into the virtual machine and executed after bootstrap.sh. 
# DO NOT run on your host machine.

set -e
is_master=$1

# this file shouldn't exist but it does. leftover from installing salt? nfi.
sudo rm -f /etc/salt/minion_id

# ensure salt can talk to github without host verification failures
#ssh-keygen -R github.com # removes any matching keys
sudo cp /vagrant/scripts/etc-known_hosts /etc/ssh/ssh_known_hosts

# configure vagrant
sudo cp /vagrant/scripts/salt/minion /etc/salt/minion

# get the builder base formula
if [ ! -d /vagrant/cloned-projects/builder-base-formula/.git ]; then
    git clone ssh://git@github.com/elifesciences/builder-base-formula /vagrant/cloned-projects/builder-base-formula
fi

if [ "$is_master" == "true" ]; then
    echo "project is master-server, skipping formula configuration"
    # generate a key for the master server. 
    # this is uploaded to the server on AWS instances and moved into place.
    # the init-master.sh script assumes it already exists
    if ! sudo test -f /root/.ssh/id_rsa; then
        sudo ssh-keygen -t rsa -f /root/.ssh/id_rsa -N ''
    fi
    exit 0
fi

# project's `salt` file is mounted at `/srv/salt/` within the guest
# by default the project's top.sls and pillar data is disabled by file naming.
# hook that up now
cd /srv/salt/ && ln -sf example.top top.sls
if [ ! -e /srv/pillar ]; then 
    sudo ln -sf /srv/salt/pillar/ /srv/pillar
fi

# TODO: CHECK ENVIRONMENT, FAIL NOISILY

echo "Restarting salt-minion"
sudo service salt-minion restart

echo "Executing salt highstate (provisioning)"
sudo salt-call state.highstate --retcode-passthrough || {
    status=$?
    echo "Error provisioning, state.highstate returned: ${status}"
}
