#!/bin/bash

set -e # everything must pass

args="$*"
module='tests'
if [ ! -z "$args" ]; then
    module="$args"
fi

export PYTHONPATH="src"
green -vv --quiet-coverage "$module"

# only report coverage if we're running a complete set of tests
if [ "tests integrations_tests" = "$module" ]; then
    # is only run if tests pass
    covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
    if [ $covered -lt 67 ]; then
        echo
        echo "FAILED this project requires at least 67% coverage"
        echo
        exit 1
    fi
fi
