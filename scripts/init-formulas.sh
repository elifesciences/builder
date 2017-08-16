#!/usr/bin/bash
# AWS MASTERLESS ONLY
# downloads and configures formulas
# Vagrant initialises the formulas in the Vagrantfile

set -eu
set -x

# space separated string of repositories to clone as a single argument
# "https://github.com/elifesciences/builder-base-formula https://github.com/elifesciences/api-dummy-formula"
formula_list=$1
pillar_repo=$2 # what secrets do I know?

# clone the private repo (whatever it's name is) into /opt/builder-private/
# REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-private ]; then
    cd /opt
    git clone "$pillar_repo" builder-private || {
        set +xv
        echo "
----------

could not clone your 'builder-private' repository:
    $pillar_repo

this means you're stuck using the dummy pillar data in builder-base-formula until
the 'builder-private' repo can be cloned and configured.

when ready, complete this process by using the 'masterless.update' command:

    ./bldr masterless.update:<stackname>

----------"

        exit 0
    }
    
else
    cd /opt/builder-private
    git clean -d --force # in vagrant, destroys any rsync'd files
    git reset --hard
    git pull
fi

# we can't use the master-server's top.sls file (and it probably shouldn't be
# there as 'top.sls' anyway), so delete it. 
rm -f /opt/builder-private/salt/top.sls


#
# handle formulas
#

formula_dir="/opt/formulas"

# the /srv/salt/ directory is where we'll link the top.sls files
# they are otherwise empty
mkdir -p "$formula_dir" /srv/salt/ /srv/salt/pillar/

echo "---
file_client: local
log_level: info
fileserver_backend:
- roots" > /etc/salt/minion

echo "file_roots:
  base:
    - /srv/salt/
    - /opt/builder-private/salt/" > /etc/salt/minion.d/file_roots.conf

# we only care about the pillar data in builder-private
echo "pillar_roots:
  base:
    - /srv/salt/pillar/
    - /opt/builder-private/pillar/" > /etc/salt/minion.d/pillar_roots.conf

# convenience. 
# this won't do anything but put the two top.sls files closer to each other
cd /srv/salt/pillar
ln -sfT /opt/builder-private/pillar/top.sls top.sls

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

    topfile="$repo_path/salt/example.top"

    # successively overwrites the top file until the last one (project formula) wins
    if [ -e "$topfile" ]; then
        cd /srv/salt 
        ln -sfT "$topfile" top.sls
    fi
}

for formula in $formula_list; do
    clone_update "$formula"
done

