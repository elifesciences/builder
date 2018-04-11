#!/bin/bash

set -e # everything must pass

envname="${1}"

if [ -z "$envname" ]; then
    echo "Must pass a label for test artifact file e.g. py27"
    exit 1
fi

export PYTHONPATH="src"
coverage run -m pytest \
    --cov=src \
    -s \
    --junitxml=build/pytest-$envname.xml \
    src/tests src/integration_tests

coverage report --fail-under=67
