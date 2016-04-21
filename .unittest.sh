#!/bin/bash
set -e
module=''
if [ ! -z "$@" ]; then
    module=".$@"
fi
nosetests tests"$module" --config .noserc
echo "* passed unittests!"
coverage report
