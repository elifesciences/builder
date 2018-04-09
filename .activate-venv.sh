#!/bin/bash
set -e

# TODO: is this still necessary?
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

# prefer python2 over python3
if [ ! -f .use-python-3.flag ]; then
    # highest installed version of py2
    python=$(which python2)
else
    # python 3.5
    python=/usr/bin/python3.5
fi

py=${python##*/} # ll: python3.5
echo "using $py"

if [ ! -e "venv/bin/$py" ]; then
    echo "could not find venv/bin/$py, recreating venv"
    rm -rf venv
fi

# create+activate venv
virtualenv --python=$python venv
source venv/bin/activate

if [ "$(uname)" = "Darwin" ]; then
    # 'ARCHFLAGS' fixes a problem with OSX refusing to compile a dependency
    export ARCHFLAGS="-Wno-error=unused-command-line-argument-hard-error-in-future"
    # at time of writing, macs dont have ipython and a lower version of Fabric
    pip install -r py2-requirements.txt
elif [ ! -f .use-python-3.flag ]; then
    # on Python2, sticking to Fabric rather than Fabric3
    pip install -r py2-requirements.txt
else
    pip install -r requirements.txt
fi
