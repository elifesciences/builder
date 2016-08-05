#!/bin/bash

set -e # everything must pass

python .prerequisites.py "$@"

# remove any old compiled python files
find src/ -name '*.pyc' -delete

# installs s3 auth plugin so we can pull boxes from a private s3 bucket
if command -v vagrant > /dev/null; then
    # 2016-08-05, custom basebox disabled until s3auth plugin fixed
	touch .no-vagrant-s3auth.flag    
    if [ ! -f .no-vagrant-s3auth.flag ]; then
        # vagrant plugin update ... doesn't work apparently
        # just calling install does
        vagrant plugin install vagrant-s3auth
    else
        echo "* the no-vagrant-s3auth flag has been set. skipping check."
    fi
fi

# generate a settings file if one doesn't exist
if [ ! -e settings.yml ]; then
    echo "* settings.yml not found, creating"
    grep -Ev '\w*##' example.settings.yml > settings.yml
fi

# activate the venv, recreating if neccessary
. .activate-venv.sh

# download the basebox from s3 if vagrant is installed
if command -v vagrant > /dev/null; then
    # 2016-08-05, custom basebox disabled until s3auth plugin fixed
    touch .no-install-basebox.flag
    if [ ! -f .no-install-basebox.flag ]; then
        vagrant box add s3://elife-builder/boxes/ elifesciences/basebox
    else
        echo "* the no-install-basebox flag is set. skipping check"
    fi
fi

printf "\n   ◕ ‿‿ ◕   all done\n\n"
