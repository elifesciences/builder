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

# skip utils.confirm() prompts during testing
export BUILDER_NON_INTERACTIVE=1

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.
# see `venv/bin/pytest` and `src/buildercore/threadbare/__init__.py`
./patched_pytest \
    $coverage_options \
    --capture=no \
    --junitxml="build/pytest-$envname.xml" \
    src/tests src/integration_tests

if [ ! -z "$coverage_options" ]; then
    echo "Checking coverage report"
    coverage report --fail-under=69
fi
