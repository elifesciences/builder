#!/usr/bin/bash
# AWS MASTERLESS ONLY
# downloads and configures formulas
# Vagrant initialises the formulas in the Vagrantfile

set -eu
set -x

clone_update() {
    repo=$1
    repo_name=${repo##*/}
    repo_path="$formula_dir/$repo_name"

    if [ -d "$repo_path" ]; then
        echo "updating $repo_name"
        cd "$repo_path"
        git pull
    else
        echo "cloning $repo_name"
        cd "$formula_dir"
        git clone "$repo" "$repo_name/"
    fi

    # tell the minion where it can find the formula's state and pillar data
    echo "    - $repo_path/salt/" >> /etc/salt/minion.d/file_roots.conf
    echo "    - $repo_path/salt/pillar/" >> /etc/salt/minion.d/pillar_roots.conf

    topfile="$repo_path/salt/example.top"

    # successively overwrites the top file until the last one (project formula) wins
    if [ -e "$topfile" ]; then
        cd "$repo_path/salt"; ln -sfT "$topfile" top.sls
    fi
}

# space separated string of repositories to clone as a single argument
# "https://github.com/elifesciences/builder-base-formula https://github.com/elifesciences/api-dummy-formula"
formula_list=$1
pillar_repo=$2 # what secrets do I know?

#
# handle formulas
#

formula_dir="/opt/formulas"

mkdir -p "$formula_dir"

echo "---
file_client: local
log_level: info
fileserver_backend:
- roots" > /etc/salt/minion

printf "file_roots:\n  base:\n" > /etc/salt/minion.d/file_roots.conf
printf "pillar_roots:\n  base:\n" > /etc/salt/minion.d/pillar_roots.conf

for formula in $formula_list; do
    clone_update "$formula"
done

#
# handle the private repo
#

# clone the private repo (whatever it's name is) into /opt/builder-private/
# REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-private ]; then
    cd /opt
    git clone "$pillar_repo" builder-private || {
        set +xv
        pubkey=$(cat /root/.ssh/id_rsa.pub)
        echo "
----------

could not clone your 'builder-private' repository:
    $pillar_repo

this means you're stuck using the dummy pillar data in builder-base-formula until
the 'builder-private' repo can be cloned and configured.

when ready, complete this process by using the 'masterless.update' command:

    ./bldr masterless.update:$stackname

----------"

        exit 0
    }
    
else
    cd /opt/builder-private
    git clean -d --force # in vagrant, destroys any rsync'd files
    git reset --hard
    git pull
fi


# TODO: replace builder-base entry in /etc/salt/minion.d/pillar_roots
# TODO: add entry in /etc/salt/minion.d/file_roots


