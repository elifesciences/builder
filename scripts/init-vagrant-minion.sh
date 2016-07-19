#!/bin/bash
# VAGRANT ONLY
# copied into the virtual machine and executed after bootstrap.sh. 
# DO NOT run on your host machine.

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

# configure vagrant
# overwrite the general purpose /etc/salt/minion file created in bootstrap.sh
sudo cp /vagrant/scripts/salt/minion /etc/salt/minion

# ensure salt can talk to github without host verification failures
#ssh-keygen -R github.com # removes any matching keys
sudo cp /vagrant/scripts/etc-known_hosts /etc/ssh/ssh_known_hosts

# get the builder base formula
if [ ! -d /vagrant/cloned-projects/builder-base-formula/.git ]; then
    git clone ssh://git@github.com/elifesciences/builder-base-formula /vagrant/cloned-projects/builder-base-formula
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
