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
