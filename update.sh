#!/bin/bash

set -e # everything must pass

python .prerequisites.py

# remove any old compiled python files
find src/ -name '*.pyc' -delete

# installs s3 auth plugin so we can pull boxes from a private s3 bucket
if [ ! -f .no-vagrant-s3auth.flag ]; then
    # vagrant plugin update ... doesn't work apparently
    # just calling install does
    vagrant plugin install vagrant-s3auth

    #if ! vagrant plugin list | grep vagrant-s3auth; then
    #    vagrant plugin install vagrant-s3auth
    #else
    #    echo "found s3 auth plugin, looking for upgrades"
    #    vagrant plugin update vagrant-s3auth
    #fi
else
    echo "* the no-vagrant-s3auth flag has been set. skipping check."
fi

# so ssh doesn't complain
#chmod 400 payload/deploy-user.pem

# so we can do ./bldr ...
chmod +x bldr

# activate the venv, recreating if neccessary
source .activate-venv.sh

# download the basebox from s3 if vagrant is installed
if [ ! -f .no-install-basebox.flag ]; then
    if which vagrant; then
        ./bldr packer.install_basebox
    fi
else
    echo "* the no-install-basebox flag is set. skipping check"
fi
