#!/bin/bash
# runs project tests
# and optionally the integration tests with BUILDER_INTEGRATION_TESTS=1.
# called by `test.sh` and `canary.sh`
set -e
args="$*"

# turn integration tests on when BUILDER_INTEGRATION_TESTS has a value.
integration_tests=false
if [ -n "$BUILDER_INTEGRATION_TESTS" ]; then
    integration_tests=true
fi

coverage_threshold=70
coverage_err="\nFAILED coverage test: $coverage_threshold%% required but exiting successfully with this warning.\n"

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.

if [ -n "$args" ]; then 
    # custom pytest arguments have been given, use those.
    ./patched_pytest -vv "$args"

elif ! $integration_tests; then
    # run the regular project tests when called without args.
    ./patched_pytest \
        -vv \
        --cov-config=.coveragerc --cov-report= --cov=src \
        --capture=sys \
        --show-capture=all \
        src/tests/

    echo "Checking coverage report"
    coverage report --fail-under="$coverage_threshold" || printf "$coverage_err"

else
    # run all tests
    ./patched_pytest \
        -vv \
        --cov-config=.coveragerc --cov-report= --cov=src \
        --capture=no \
        --junitxml="build/pytest-py3.xml" \
        src/tests src/integration_tests

    echo "Checking coverage report"
    coverage report --fail-under="$coverage_threshold" || printf "$coverage_err"
fi
