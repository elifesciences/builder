#!/bin/bash

set -e # everything must pass

envname="${1}"

if [ -z "$envname" ]; then
    echo "Must pass a label for test artifact file e.g. py27"
    exit 1
fi

echo "Running tests"
export PYTHONPATH="src"

# skip utils.confirm() prompts during testing
export BUILDER_NON_INTERACTIVE=1

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.
# see `venv/bin/pytest` and `src/buildercore/threadbare/__init__.py`
./patched_pytest \
    --cov-config=.coveragerc --cov-report= --cov=src \
    --capture=no \
    --junitxml="build/pytest-$envname.xml" \
    src/tests src/integration_tests

echo "Checking coverage report"
coverage report --fail-under=70 || (
    echo "FAILED coverage report, but exiting successfully with this warning."
)
