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
    echo "Usage: ./bootstrap.sh <salt_version> <salt_minion_id> <install_salt_master> [salt_master_ipaddr]"
    echo "Example: ./bootstrap.sh 2017.7.x journal--end2end--1 false 10.0.0.1"
    exit 1
fi

startswith() { 
    string=$1
    prefix=$2
    case "$string" in "$prefix"*) true;; *) false;; esac;
}

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
    # we're installing for the first time if we can't find a /root/events.log file.
    # this file is populated after successful salt installation or upgrade and deleted during AMI creation.
    installing=true
else
    if ! (salt-minion --version | grep "$version"); then
        upgrading=true
    fi
fi

install_python=false
install_git=false

if ! command -v python3; then
    # python3 not found
    install_python=true
fi

if ! command -v git; then
    # git not found
    install_git=true
fi

if ($install_python || $install_git); then
    apt-get update -y -q
fi

if $upgrading; then
    # old versions of this file interfere with the salt upgrade process as they 404 software as soon as it falls out of support.
    rm -f /etc/apt/sources.list.d/saltstack.list
fi

if $install_python; then
    # confdef: If conf file modified and the version in the package changed, choose the default action without prompting. 
    #          If there is no default action, stop to ask the user unless '--force-confnew' or '--force-confold' given.
    # confold: If conf file modified and the version in the package changed, keep the old version without prompting
    apt-get install \
        python3 python3-dev python3-pip python3-setuptools \
        -y -q --no-install-recommends \
        -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

    python3 -m pip config set global.progress_bar off
    python3 -m pip config set global.disable-pip-version-check true

    # lsh@2023-05-17: why do we need setuptools ?
    python3 -m pip install pip wheel setuptools --upgrade

    # record an entry about when python3 was installed/upgraded.
    # presence of this entry is used to skip this section in future, unless forced with a flag.
    echo "$(date -I) -- installed python3" >> /root/events.log;
fi

if $install_git; then
    apt-get install git -y -q
fi

# workaround for https://github.com/saltstack/salt-bootstrap/issues/2027
# also see salt_bootstrap.sh -r 
mkdir -p /etc/apt/keyrings
curl -fsSL https://packages.broadcom.com/artifactory/api/security/keypair/SaltProjectKey/public | sudo tee /etc/apt/keyrings/salt-archive-keyring.pgp
curl -fsSL https://github.com/saltstack/salt-install-guide/releases/latest/download/salt.sources | sudo tee /etc/apt/sources.list.d/salt.sources

pin_version="$version"
if [[ "$version" != *.* ]]; then
    pin_version="$version.*"
fi

echo "Package: salt-*
Pin: version $pin_version
Pin-Priority: 1001" | sudo tee /etc/apt/preferences.d/salt-pin-1001

# salt-minion
if ($installing || $upgrading); then
    echo "Bootstrap salt $version"
    wget -L https://github.com/saltstack/salt-bootstrap/releases/latest/download/bootstrap-salt.sh --output-document salt_bootstrap.sh --no-verbose

    # -F      Allow copied files to overwrite existing(config, init.d, etc)
    # -c      Temporary configuration directory
    # onedir  a single binary salt installation, only supported installation type since v3006.0
    # -M      Also install master
    sh salt_bootstrap.sh -r -F -c /tmp onedir "$version"
else
    echo "Skipping minion bootstrap, found: $(salt-minion --version)"
fi

# salt-master
if [ "$install_master" = "true" ]; then
    # salt is not installed or the version installed is old
    if ! (command -v salt-master > /dev/null && salt-master --version | grep "$version"); then
        # master not installed
        sh salt_bootstrap.sh -r -F -M -c /tmp onedir "$version"
    else
        echo "Skipping master bootstrap, found: $(salt-master --version)"
    fi
fi


# install salt dependencies
# some Salt states require extra libraries to be installed before calling highstate.
# salt builtins: https://github.com/saltstack/salt/blob/master/requirements/static/pkg/py3.9/linux.txt
if ($installing || $upgrading); then
    # lsh@2023-05-12: version pins are just because they're the latest stable, nothing significant.
    salt-pip install "docker~=7.1" "pymysql~=1.0"
fi


# record some basic info after the above successfully completes
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
# remove any existing keys for github.com
ssh-keygen -R github.com
ssh-keygen -R 192.30.252.128
# append this to the global known hosts file
# - https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# shellcheck disable=SC2129
# - SC2129 (style): Consider using { cmd1; cmd2; } >> file instead of individual redirects.
if ! grep AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl /etc/ssh/ssh_known_hosts; then
    echo "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" >> /etc/ssh/ssh_known_hosts
    echo "github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=" >> /etc/ssh/ssh_known_hosts
    echo "github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=" >> /etc/ssh/ssh_known_hosts
fi

