#!/bin/bash
set -e
module=''
if [ ! -z "$@" ]; then
    module=".$@"
fi

export PYTHONPATH="src"
green --run-coverage tests"$module"

# only test coverage if we running complete set of tests
if [ -z "$module" ]; then
    # is only run if tests pass
    covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
    if [ $covered -le 50 ]; then
        echo
        echo "FAILED this project requires at least 50% coverage"
        echo
        exit 1
    fi
fi
