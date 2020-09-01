#!/bin/bash
# updates dependencies then runs the tests
set -e
. update-dependencies.sh 
. .run-tests.sh
