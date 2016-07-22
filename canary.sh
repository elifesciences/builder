#!/bin/bash
set -e # everything must pass
. .upgrade-deps.sh # upgrade all deps to latest version
. .unittest.sh # run the tests
