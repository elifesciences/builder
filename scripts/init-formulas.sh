#!/usr/bin/bash
# AWS MASTERLESS ONLY
# downloads and configures formulas using /etc/build-vars.json.b64
# Vagrant initialises the formulas in the Vagrantfile

set -eu
set -x

# space separated string of repositories to clone as a single argument
# "https://github.com/elifesciences/builder-base-formula https://github.com/elifesciences/api-dummy-formula"
formula_list=$1
formula_dir="/opt/formulas"

mkdir -p "$formula_dir" /srv/salt/ /srv/pillar/

echo "---
file_client: local
log_level: info
fileserver_backend:
- roots
file_roots:
  base: []
pillar_roots:
  base: []"  > /tmp/minion # > /etc/salt/minion

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
        
    echo "  - $repo_path/salt/" >> /etc/salt/minion.d/file_roots.conf
    echo "  - $repo_path/salt/pillar/" >> /etc/salt/minion.d/pillar_roots.conf

    topfile="$repo_path/salt/example.top"
    pillarfile="$repo_path/salt/pillar/example.pillar"
    
    # successively overwrites the top files until the last one (project formula) wins
    if [ -e "$topfile" ]; then
        # /srv/salt/ and /srv/pillar/ are Salt's default dirs for top files
        cd /srv/salt/; ln -sfT "$topfile" top.sls
        cd /srv/pillar/; ln -sfT "$pillarfile" top.sls
    fi
}

echo "file_roots:" > /etc/salt/minion.d/file_roots.conf
echo "pillar_roots:" > /etc/salt/minion.d/pillar_roots.conf

for formula in $formula_list; do
    clone_update "$formula"
done

