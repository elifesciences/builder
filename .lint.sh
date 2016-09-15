#!/bin/bash
set -e

echo "* calling pyflakes"
# if grep has output, fail
if pyflakes src/ | grep -v src/fabfile.py; then exit 1; fi

echo "* calling pylint"
# E1129=doesn't like Fabric's context manager
pylint -E src/* --disable=E1129 --rcfile=.pylintrc
echo "* passed initial lint!"
