#!/bin/bash
set -e
# E1129=doesn't like Fabric's context manager
pylint -E src/* --disable=E1129 --rcfile=.pylintrc
echo "* passed initial lint!"
