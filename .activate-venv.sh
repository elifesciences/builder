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
    python=$(which python2 python2.7 | head -n 1)
else
    # python 3.6, 18.04
    # python 3.8, 20.04
    python=$(which python3.8 python3.6 python3 | head -n 1)
fi

py=${python##*/} # "python3.6"
echo "using $py"

if [ ! -e "venv/bin/$py" ]; then
    echo "could not find venv/bin/$py, recreating venv"
    rm -rf venv
fi

# create+activate venv
if [ -f .use-python-3.flag ]; then
    "$python" -m venv venv
else
    # Python2
    virtualenv --python=$python venv
fi
source venv/bin/activate
# pip 20.3.4 is the last version of pip to support python2
pip install wheel "pip==20.3.4" --upgrade

if [ ! -f .use-python-3.flag ]; then
    # on Python2, sticking to Fabric rather than Fabric3
    pip install -r py2-requirements.txt
else
    pip install -r requirements.txt
fi
