#!/bin/bash
# VAGRANT ONLY
# copied into the virtual machine and executed after bootstrap.sh. 
# DO NOT run on your host machine.

set -e

echo "-----------------------------"

# ensure the gitfs backend deps are installed
# this only needs to be done on the master or masterless minions
#sudo apt-get install python-git -y
sudo apt-get install python-setuptools python-dev libgit2-dev libffi-dev python-git -y

# ensure salt can talk to github without host verification failures
#ssh-keygen -R github.com # removes any matching keys
sudo cp /vagrant/scripts/etc-known_hosts /etc/ssh/ssh_known_hosts

sudo cp /vagrant/scripts/salt/minion /etc/salt/minion

# project's `salt` file is mounted at `/srv/salt/` within the guest
# by default the project's top.sls and pillar data is disabled by file naming.
# hook that up now
cd /srv/salt/ && ln -sf example.top top.sls && cd ../../
if [ ! -e /srv/pillar ]; then sudo ln -sf /srv/salt/pillar/ /srv/pillar; fi

echo "Restarting salt-minion"
sudo service salt-minion restart

# this file shouldn't exist but it does. leftover from installing salt? nfi.
sudo rm -f /etc/salt/minion_id

echo "Executing salt highstate (provisioning)"
sudo salt-call state.highstate -l debug || {
    status=$?
    echo "Error provisioning, state.highstate returned: ${status}"
}
