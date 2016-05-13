#!/bin/bash
# copied into the virtual machine and executed after bootstrap.sh. 
# DO NOT run on your host machine.

set -e

echo "-----------------------------"

sudo cp /vagrant/scripts/salt/minion /etc/salt/minion
sudo cp /vagrant/scripts/salt/srv-pillar-top.sls /srv/pillar/top.sls
echo "Restarting salt-minion"
sudo salt-minion -d # TODO: necessary?
sudo service salt-minion restart

# this file shouldn't exist but it does. leftover from installing salt? nfi.
sudo rm -f /etc/salt/minion_id

echo "Executing salt highstate (provisioning)"
sudo salt-call state.highstate || {
    status=$?
    echo "Error provisioning, state.highstate returned: ${status}"
}


