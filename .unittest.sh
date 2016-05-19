#!/bin/bash
set -e
module=''
if [ ! -z "$@" ]; then
    module=".$@"
fi
nosetests tests"$module" --config .noserc
echo "* passed unittests!"
coverage report

covered=$(coverage report | grep TOTAL | awk '{print $6}' | sed 's/%//')
if [ $covered -le 30 ]; then
    echo
    echo "FAILED this project requires at least 30% coverage"
    echo
    exit 1
fi
