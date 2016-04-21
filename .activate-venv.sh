#!/bin/bash
set -e

# always recreate the virtualenv by default
# UNLESS a flag has been set
if [ ! -f .no-delete-venv.flag ]; then
    if [ -d venv ]; then
        # for some reason this venv seems to be flaky
        # destroying and rebuilding fixes some odd problems
        rm -rf ./venv
    fi
else
    echo "* the no-delete-venv flag is set. preserving venv"
fi

if [ ! -d venv ]; then
    # build venv if one doesn't exist
    virtualenv --python=`which python2` venv
fi

# 'ARCHFLAGS' fixes a problem with OSX refusing to compile a dependency
export ARCHFLAGS="-Wno-error=unused-command-line-argument-hard-error-in-future"

source venv/bin/activate
pip install -r requirements.txt
