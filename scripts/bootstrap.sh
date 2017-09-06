#!/bin/bash
# *ALL INSTANCES*
# copied into the virtual machine and executed. DO NOT run on your host machine.

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

echo "-----------------------------"

if [ ! "$#" -ge 3 ]; then
    echo "Usage: ./bootstrap.sh <version> <minion_id> <install_master> [master_ipaddr]"
    echo "Example: ./bootstrap.sh 2016.3.4 journal--end2end--1 false 10.0.0.1"
    exit 1
fi

version=$1
minion_id=$2
install_master=$3
master_ipaddr=${4:-""} # optional 4th argument. masterless minions do not use this.

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

upgrade_python=false
install_git=false

# Python is such a hard dependency of Salt that we have to upgrade it outside of 
# Salt to avoid changing it while it is running

if ! command -v python2.7; then
    # python2 not found
    upgrade_python=true
else
    # python found, check installed version
    python_version=$(dpkg-query -W --showformat='${Version}' python2.7) # e.g. 2.7.5-5ubuntu3
    if dpkg --compare-versions "$python_version" lt 2.7.12; then
        # we used this, which is not available anymore, to provide a more recent Python 2.7
        # let's remove it to avoid apt-get update errors
        rm -f /etc/apt/sources.list.d/fkrull-deadsnakes-python2_7-trusty.list

        # provides python2.7[.13] package and some dependencies
        add-apt-repository ppa:jonathonf/python-2.7

        # provides a recent python-urllib3 (1.13.1-2) because:
        # libpython2.7-stdlib : Breaks: python-urllib3 (< 1.9.1-3) but 1.7.1-1ubuntu4 is to be installed
        # due to the previous PPA
        add-apt-repository ppa:ross-kallisti/python-urllib3
        upgrade_python=true
    fi
fi

if ! dpkg -l git; then
    install_git=true
fi

if ($upgrade_python || $install_git); then
    apt-get update -y
fi

if $upgrade_python; then
    apt-get install python2.7 python2.7-dev -y
    # virtual envs have to be recreated
    find /srv /opt -depth -type d -name venv -exec rm -rf "{}" \;
fi

if $install_git; then
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
if [ ! -e /etc/salt/minion ]; then
    printf "master: %s\nlog_level: info\n" "$master_ipaddr" > /etc/salt/minion
else
    echo "Not overwriting existing /etc/salt/minion"
fi

echo "$minion_id" > /etc/salt/minion_id
echo "mysql.unix_socket: '/var/run/mysqld/mysqld.sock'" > /etc/salt/minion.d/mysql-defaults.conf

#  service restart necessary as we've changed the minion's configuration
service salt-minion restart


# generate a key for the root user
# in AWS this is uploaded to the server and moved into place prior to calling 
# this script. in Vagrant it must be created.
if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -t rsa -f /root/.ssh/id_rsa -N ''
fi
touch /root/.ssh/known_hosts

# after bootstrap.sh and before salt's highstate, we may need to talk to github

# ensure salt can talk to github without host verification failures
ssh-keygen -R github.com # removes any existing keys
# append this to the global known hosts file
echo "github.com,192.30.252.128 ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==" >> /etc/ssh/ssh_known_hosts

# run the daily cron job
# this ensures security patches are run for machines that are only brought 
# online temporarily to run tests
if [ ! -e "/root/updated-$(date -I)" ]; then
    touch "/root/updated-$(date -I)" && run-parts /etc/cron.daily &
fi

