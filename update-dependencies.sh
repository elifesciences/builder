#!/bin/bash
# updates Pipfile.lock and regenerates the requirements.txt file

set -ex

# create/update existing venv
. .activate-venv.sh

# updates the Pipfile.lock file and then installs the newly updated dependencies.
# the envvar is necessary otherwise pipenv will use it's own .venv directory.
VIRTUAL_ENV="venv" pipenv update --dev

datestamp=$(date -I)
echo "# file generated $datestamp - see update-dependencies.sh" > requirements.txt
pipenv run pip freeze >> requirements.txt
