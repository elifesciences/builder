#!/bin/bash
set -e
modules='tests'
if [ ! -z "$*" ]; then
    modules="$*"
fi

export PYTHONPATH="src"
green --run-coverage $modules

# only report coverage if we're running a complete set of tests
if [ "tests integrations_tests" = "$modules" ]; then
    # is only run if tests pass
    covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
    if [ $covered -lt 67 ]; then
        echo
        echo "FAILED this project requires at least 67% coverage"
        echo
        exit 1
    fi
fi
