#!/usr/bin/bash
# AWS MASTERLESS ONLY
# downloads and configures formulas.
# note: Vagrant's equivalent lives in the Vagrantfile.
# note: master-server instances are typically *not* masterless.

set -eu
set -x

# space separated string of repositories to clone as a single argument
# "https://github.com/elifesciences/builder-base-formula https://github.com/elifesciences/api-dummy-formula"
formula_list=$1
pillar_repo=$2 # what secrets do I know?
configuration_repo=$3 # what configuration do I know?

# clone the private repo (whatever it's name is) into /opt/builder-private/
# REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-private ]; then
    cd /opt
    git clone "$pillar_repo" builder-private --quiet
else
    cd /opt/builder-private
    git clean -d --force # remove any unknown files
    git reset --hard # revert any changes to known files
    git pull || {
        # known case - we've set a specific revision and cannot pull
        echo "builder-private is pinned, could not update to head"
    }
fi

# clone the configuration repo into /opt/builder-configuration/
# REQUIRES CREDENTIALS!
if [ ! -d /opt/builder-configuration ]; then
    cd /opt
    git clone "$configuration_repo" builder-configuration --quiet
else
    cd /opt/builder-configuration
    git clean -d --force # remove any unknown files
    git reset --hard # revert any changes to known files
    git pull || {
        # known case - we've set a specific revision and cannot pull
        echo "builder-configuration is pinned, could not update to head"
    }
fi

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
    - /opt/builder-configuration/salt/
    - /opt/builder-private/salt/" > /etc/salt/minion.d/file_roots.conf

# we only care about the pillar data in builder-private
echo "pillar_roots:
  base:
    - /srv/salt/pillar/
    - /opt/builder-configuration/pillar/
    - /opt/builder-private/pillar/" > /etc/salt/minion.d/pillar_roots.conf

clone_update() {
    repo=$1
    repo_name=${repo##*/}
    repo_path="$formula_dir/$repo_name"

    if [ -d "$repo_path" ]; then
        echo "updating $repo_name"
        cd "$repo_path"
        git clean -d --force # remove any unknown files
        git reset --hard # revert any changes to known files
        git pull || {
            # known case - we've set a specific revision and cannot pull
            echo "$repo_name is pinned, could not update to head"
        } 
    else
        echo "cloning $repo_name"
        cd "$formula_dir"
        git clone "$repo" "$repo_name/" --quiet
    fi

    # tell the minion where it can find the formula's state and pillar data
    echo "    - $repo_path/salt/" >> /etc/salt/minion.d/file_roots.conf

    if [ "${BUILDER_TOPFILE}" != "" ]; then
        topfile="$repo_path/salt/${BUILDER_TOPFILE}"
    else
        topfile="$repo_path/salt/example.top"
    fi

    # successively overwrites the top file until the last one (project formula) wins
    #if [ -e "$topfile" ]; then
    cd /srv/salt 
    ln -sfT "$topfile" top.sls
    #fi
}

for formula in $formula_list; do
    clone_update "$formula"
done

