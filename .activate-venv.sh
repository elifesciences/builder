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

# TODO: legacy, remove once flag is removed from all environments
rm -f .use-python-3.flag

# "python3", typically points to the latest version of python3 installed. varies by distribution
# "python3.5", Ubuntu 16.04
# "python3.6", Ubuntu 18.04
python=$(which python3 python3.6 python3.5 | head -n 1)

py=${python##*/} # ll: python3.6
echo "using $py"

if [ ! -e "venv/bin/$py" ]; then
    echo "could not find venv/bin/$py, recreating venv"
    rm -rf venv
fi

# create+activate venv
"$python" -m venv venv
source venv/bin/activate

pip install -r requirements.txt
