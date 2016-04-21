#!/bin/bash
# copied into the virtual machine and executed after bootstrap.sh. 
# DO NOT run on your host machine.

start_seconds="$(date +%s)"

sudo cp /vagrant/salt/vagrant-minion /etc/salt/minion
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

echo "-----------------------------"

end_seconds="$(date +%s)"
echo "Provisioning complete in "$(expr $end_seconds - $start_seconds)" seconds"
