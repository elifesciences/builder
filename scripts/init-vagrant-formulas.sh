#!/bin/bash
# VAGRANT ONLY
# copied into the virtual machine and executed after bootstrap.
# run as root
# DO NOT run on your host machine.
# see scripts/init-formulas.sh for non-vagrant masterless instances

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

minion_id=$1

# ELPP-3601: Vagrant machines run masterless and don't need salt-minion running
systemctl stop salt-minion 2> /dev/null

# link up the project formula mounted at /project
# NOTE: these links will be overwritten if this a master-server instance
# lsh@2024-03-04: salt 3006.6 ignores sylinks, the full path is now used in the minion.template
#ln -sfn /project/salt /srv/salt
#ln -sfn /project/salt/pillar /srv/pillar

# this allows you to serve up projects like the old builder used
# excellent for project creation without all the formula overhead
# lsh@2024-03-04: salt 3006.6 ignores sylinks, the full path is now used in the minion.template
#ln -sfn /vagrant/custom-vagrant /srv/custom

# by default the project's top.sls is disabled by file naming. hook that up here
(
    cd /project/salt
    ln -sf "${BUILDER_TOPFILE:-example.top}" top.sls
)

# vagrant makes all formula dependencies available, including builder base formula

# overwrite the general purpose /etc/salt/minion file created above 
# with a custom one for masterless environments only
cp /vagrant/scripts/salt/minion.template /etc/salt/minion
custom_minion_file="/vagrant/scripts/salt/$minion_id.minion"
if [ -e "$custom_minion_file" ]; then
    # this project requires a custom minion file. use that instead
    cp "$custom_minion_file" /etc/salt/minion
else
    echo "couldn't find $custom_minion_file"
fi
