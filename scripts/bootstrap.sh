#!/bin/bash
# *ALL INSTANCES*
# run as root
# copied/uploaded onto the virtual machine and executed. DO NOT run on your host machine.

set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps

export DEBIAN_FRONTEND=noninteractive # no ncurses prompts

echo "-----------------------------"

if [ ! "$#" -ge 3 ]; then
    echo "Usage: ./bootstrap.sh <version> <minion_id> <install_master> [master_ipaddr]"
    echo "Example: ./bootstrap.sh 2017.7.x journal--end2end--1 false 10.0.0.1"
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

upgrade_python2=false
upgrade_python3=false
install_git=false

# Python is such a hard dependency of Salt that we have to upgrade it outside of 
# Salt to avoid changing it while it is running

# TODO: remove this block once our python2 dependency is gone
if ! command -v python2.7; then
    # python2 not found
    upgrade_python2=true
else
    # python2 found, check installed version
    python_version=$(dpkg-query -W --showformat="\${Version}" python2.7) # e.g. 2.7.5-5ubuntu3
    if dpkg --compare-versions "$python_version" lt 2.7.12; then
        # we used this, which is not available anymore, to provide a more recent Python 2.7
        # let's remove it to avoid apt-get update errors
        rm -f /etc/apt/sources.list.d/fkrull-deadsnakes-python2_7-trusty.list

        # provides python2.7[.13] package and some dependencies
        add-apt-repository -y ppa:jonathonf/python-2.7

        # provides a recent python-urllib3 (1.13.1-2) because:
        # libpython2.7-stdlib : Breaks: python-urllib3 (< 1.9.1-3) but 1.7.1-1ubuntu4 is to be installed
        # due to the previous PPA
        add-apt-repository -y ppa:ross-kallisti/python-urllib3
        upgrade_python2=true
    fi

    # if flag present, upgrade python
    if [ -f /root/upgrade-python.flag ]; then
        upgrade_python2=true
    fi
fi

if ! command -v python3; then
    # python3 not found
    upgrade_python3=true
else
    # python 3 found but have our other py3 dependencies been installed?
    if ! grep "installed/upgraded python3" /root/events.log; then
        upgrade_python3=true
    fi
fi

if ! dpkg -l git; then
    # git not found
    install_git=true
fi

if ($upgrade_python2 || $upgrade_python3 || $install_git); then
    apt-get update -y -q
fi


# flag we can toggle to disable installation of python2 and python2 libs.
# set to `false` once all formulas and formula code has been updated.
elife_depends_on_python2=true

if $upgrade_python2; then

    if $elife_depends_on_python2; then
        echo "eLife still has formulas that depend on Python2!"
        apt-get install python2.7 python2.7-dev -y -q

        # virtualenvs have to be recreated
        #find /srv /opt -depth -type d -name venv -exec rm -rf "{}" \;

        # install/upgrade pip+setuptools
        apt-get install python-pip python-setuptools --no-install-recommends -y -q
        python2.7 -m pip install pip setuptools --upgrade --progress-bar off
    fi

    # remove flag, if it exists
    rm -f /root/upgrade-python.flag
fi

if $upgrade_python3; then

    # confdef: If conf file modified and the version in the package changed, choose the default action without 
    # prompting. If there is no default action, stop to ask the user unless '--force-confnew' or '--force-confold' given
    # confold: If conf file modified and the version in the package changed, keep the old version without prompting
    apt-get install \
        python3 python3-dev python3-pip python3-setuptools \
        -y -q --no-install-recommends \
        -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

    # --progress-bar off -- this option only available since pip 10.0. 16.04 has pip 8 by default
    python3 -m pip install pip setuptools --upgrade

    # some Salt states require libraries to be installed before calling highstate
    python3 -m pip install "docker[tls]==4.1.0" --progress-bar off

    # record an entry about when python3 was installed/upgraded
    # presence of this entry is used to skip this section in future, unless forced with a flag
    if [ -f /root/upgrade-python3.flag ]; then
        echo "$(date -I) -- installed/upgraded python3 (forced)" >> /root/events.log;
    else
        echo "$(date -I) -- installed/upgraded python3" >> /root/events.log;
    fi

    # remove 'force upgrade' flag, if it exists
    rm -f /root/upgrade-python3.flag
fi

if $install_git; then
    apt-get install git -y -q
fi


# salt-minion
if ($installing || $upgrading); then
    echo "Bootstrap salt $version"
    wget -O salt_bootstrap.sh https://bootstrap.saltstack.com --no-verbose

    # -x  Changes the Python version used to install Salt.
    # -P  Allow pip based installations.
    # -F  Allow copied files to overwrite existing(config, init.d, etc)
    # -c  Temporary configuration directory
    # -M  Also install master
    # https://github.com/saltstack/salt-bootstrap/blob/develop/bootstrap-salt.sh
    #sh salt_bootstrap.sh -x python3 -P -F -c /tmp stable "$version"
    sh salt_bootstrap.sh -P -F -c /tmp stable "$version"
else
    echo "Skipping minion bootstrap, found: $(salt-minion --version)"
fi


# salt-master
if [ "$install_master" = "true" ]; then
    # salt is not installed or the version installed is old
    if ! (command -v salt-master > /dev/null && salt-master --version | grep "$version"); then
        # master not installed
        #sh salt_bootstrap.sh -x python3 -P -F -M -c /tmp stable "$version"
        sh salt_bootstrap.sh -P -F -M -c /tmp stable "$version"
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi


# record some basic provisioning info after the above successfully completes
if $installing; then echo "$(date -I) -- installed salt $version" >> /root/events.log; fi
if $upgrading; then echo "$(date -I) -- upgraded salt to $version" >> /root/events.log; fi


# BUG: during a minion's re-mastering the `master: ...` value may get reset if the instance is 
# updated by another process before the old master is turned off.
# reset the minion config and
# put minion id in dedicated file else salt keeps recreating file
printf "master: %s\\nlog_level: info\\n" "$master_ipaddr" > /etc/salt/minion
echo "$minion_id" > /etc/salt/minion_id
echo "mysql.unix_socket: '/var/run/mysqld/mysqld.sock'" > /etc/salt/minion.d/mysql-defaults.conf
grains=
while IFS='=' read -r variable_name grain_value ; do
    grain_name=${variable_name#grain_} # delete `grain_`
    printf -v grain_line "%s: %s\n" "$grain_name" "$grain_value"
    grains+="${grain_line}"
done < <(env | grep '^grain_.*')
echo "$grains" > /etc/salt/grains

# restart salt-minion. necessary as we may have changed minion's configuration
systemctl restart salt-minion 2> /dev/null

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

