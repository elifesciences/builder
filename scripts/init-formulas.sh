#!/usr/bin/python
# AWS MASTERLESS ONLY
# downloads and configures formulas using /etc/build-vars.json.b64
# Vagrant initialises the formulas in the Vagrantfile

set -eu
set -x

# init formulas

# foo=github.com/elifesciences/foo-formula,builder-base-formula=
formula_list=$1
formula_dir="/opt/formulas/"

mkdir -p "$formula_dir"

echo "---
file_client: local
log_level: info
fileserver_backend:
- roots
file_roots:
  base: []
pillar_roots:
  base: []" > /etc/salt/minion

function clone_update {
    repo=$1
    repo_name=${repo##*/}
    repo_path="$formula_dir/$repo_name"
    
    echo "  - $repo_path/salt/" >> /etc/salt/minion.d/file_roots.conf
    echo "  - $repo_path/salt/pillar/" >> /etc/salt/minion.d/pillar_roots.conf
    
    if [ -d "$repo_path" ]; then
        echo "updating $repo_name"
        cd "$repo_path"
        git pull
    else
        echo "cloning $repo_name"
        git clone $repo $repo_name/
    fi
}

echo "file_roots:" > /etc/salt/minion.d/file_roots.conf
echo "pillar_roots:" > /etc/salt/minion.d/pillar_roots.conf

for formula in $formula_list; do
    clone_update $formula
done

# TODO: link to correct top.sls files
# vagrant does this:
#cd /srv/salt/ && ln -sf example.top top.sls
# but I want to do away with /srv/salt. perhaps pass target repo in as a param?
