#!/bin/bash

set -e # everything must pass

python .prerequisites.py "$@"

# remove any old compiled python files
find src/ -name '*.pyc' -delete

# activate the venv, recreating if neccessary
. .activate-venv.sh

printf "\\n   ◕ ‿‿ ◕   all done\\n\\n"
