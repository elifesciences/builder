#!/bin/bash
set -e # everything must pass
. .upgrade-deps.sh # upgrade all deps to latest version
. .run-tests.sh # run the tests
