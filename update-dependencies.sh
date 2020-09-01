#!/bin/bash
# updates Pipfile.lock and regenerate the requirements.txt file

set -ex

# create/update existing venv
. .activate-venv.sh

# pipenv obeys an explicit venv
export VIRTUAL_ENV="venv"

# updates the Pipfile.lock file and then installs the newly updated dependencies
pipenv update --dev

datestamp=$(date -I)
echo "# file generated $datestamp - see update-dependencies.sh" > requirements.txt
pipenv run pip freeze >> requirements.txt
