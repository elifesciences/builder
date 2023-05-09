#!/bin/bash
set -e

python3 .prerequisites.py "$@"

# remove any old compiled python files.
find src/ -name '*.pyc' -delete

# installs tfenv and the versions of terraform required.
. install-terraform.sh

# activate the venv, recreating it if neccessary.
. .activate-venv.sh

printf "\\nall done\\n\\n"
