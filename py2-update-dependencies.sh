#!/bin/bash
# updates py2-Pipfile.lock and regenerates the py2-requirements.txt file
set -e

# create/update existing venv
rm -rf venv/

# builder needs to support python2 for the time being
virtualenv --python=python2 venv

# prefer using wheels to compilation
source venv/bin/activate
pip install wheel "pip==20.3.4" --upgrade

# updates the py2-Pipfile.lock file and then installs the newly updated dependencies.
# the envvar is necessary otherwise pipenv will use it's own .venv directory.
VIRTUAL_ENV="venv" PIPENV_PIPFILE="py2-Pipfile" pipenv update --dev

datestamp=$(date -I)
echo "# file generated $datestamp - see py2-update-dependencies.sh" > py2-requirements.txt
VIRTUAL_ENV="venv" PIPENV_PIPFILE="py2-Pipfile" pipenv run pip freeze >> py2-requirements.txt
