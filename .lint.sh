#!/bin/bash
set -e
# E1129=doesn't like Fabric's context manager
pylint -E src/* salt/salt/_modules/* --disable=E1129
echo "* passed initial lint!"
