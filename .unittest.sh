#!/bin/bash
set -e
module=''
if [ ! -z "$@" ]; then
    module=".$@"
fi

export PYTHONPATH="src"
green --run-coverage tests"$module"

# is only run if tests pass
covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
if [ $covered -le 50 ]; then
    echo
    echo "FAILED this project requires at least 50% coverage"
    echo
    exit 1
fi
