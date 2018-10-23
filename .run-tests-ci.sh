#!/bin/bash

set -e # everything must pass

envname="${1}"

if [ -z "$envname" ]; then
    echo "Must pass a label for test artifact file e.g. py27"
    exit 1
fi

echo "Running tests"
export PYTHONPATH="src"
if [ "$envname" = "py27" ]; then
    coverage_options="--cov-config=.coveragerc --cov-report= --cov=src"
else
    coverage_options=
fi
pytest \
    $coverage_options
    -n 4 \
    --dist=loadscope \
    -s \
    --junitxml="build/pytest-$envname.xml" \
    src/tests src/integration_tests

if [ ! -z "$coverage_options" ]; then
    echo "Checking coverage report"
    coverage report --fail-under=50
fi
