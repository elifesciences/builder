#!/bin/bash

set -e # everything must pass

python .prerequisites.py "$@"

# remove any old compiled python files
find src/ -name '*.pyc' -delete

# generate a settings file if one doesn't exist
. .settings.sh

# activate the venv, recreating if neccessary
. .activate-venv.sh

printf "\n   ◕ ‿‿ ◕   all done\n\n"
