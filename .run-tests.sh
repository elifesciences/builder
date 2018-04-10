#!/bin/bash

set -e # everything must pass

args="$@"
modules='tests'
if [ ! -z "$args" ]; then
    modules="$args"
fi

export PYTHONPATH="src"
for m in $modules; do
    green -vv --quiet-coverage "$m"
done

# only report coverage if we're running a complete set of tests
if [ "tests integration_tests" = "$module" ]; then
    # is only run if tests pass
    covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
    if [ $covered -lt 67 ]; then
        echo
        echo "FAILED this project requires at least 67% coverage"
        echo
        exit 1
    fi
fi
