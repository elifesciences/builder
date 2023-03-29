#!/bin/bash
# runs project tests
# and optionally the integration tests with BUILDER_INTEGRATION_TESTS=1.
# called by `test.sh` and `canary.sh`
set -e
args="$*"

# holdover from py2/py3/tox days.
envname="py3"

# prevent any stdin prompts still hanging around in tests.
# lsh@2023-03-29: these should all be fixed now but haven't tested.
export BUILDER_NON_INTERACTIVE=1

# if the environment variable BUILDER_INTEGRATION_TESTS has a value, turn integration tests on.
integration_tests=false
if [ -n "$BUILDER_INTEGRATION_TESTS" ]; then
    integration_tests=true
fi

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.
# see `venv/bin/pytest` and `src/buildercore/threadbare/__init__.py`

if [ -n "$args" ]; then 
    # a path or custom pytest arguments have been given, use those.
    ./patched_pytest -vv "$args"
    exit 0

elif ! $integration_tests; then
    # run the regular project project tests when called without args.
    ./patched_pytest -vv src/tests/
    exit 0

else
    # run all tests
    ./patched_pytest \
        -vv \
        --cov-config=.coveragerc --cov-report= --cov=src \
        --capture=no \
        --junitxml="build/pytest-$envname.xml" \
        src/tests src/integration_tests

    echo "Checking coverage report"
    threshold=70
    coverage report --fail-under="$threshold" || (
        echo "FAILED coverage test of $threshold%, but exiting successfully with this warning."
    )

fi
