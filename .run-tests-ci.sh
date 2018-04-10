#!/bin/bash

set -e # everything must pass

envname="${1:-default}"

export PYTHONPATH="src"
pytest --junitxml=build/pytest-$envname.xml src/tests
pytest --junitxml=build/pytest-$envname.xml src/integration_tests

covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
if [ $covered -lt 67 ]; then
    echo
    echo "FAILED this project requires at least 67% coverage"
    echo
    exit 1
fi
