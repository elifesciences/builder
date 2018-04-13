#!/bin/bash

set -e # everything must pass

python .prerequisites.py "$@"

# remove any old compiled python files
find src/ -name '*.pyc' -delete

# generate a settings file if one doesn't exist
if [ ! -e settings.yml ]; then
    echo "* settings.yml not found, creating"
    grep -Ev '\w*##' example.settings.yml > settings.yml
fi

# activate the venv, recreating if neccessary
. .activate-venv.sh

printf "\n   ◕ ‿‿ ◕   all done\n\n"
