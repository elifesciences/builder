#!/bin/bash

set -e # everything must pass

# upgrade all deps to latest version
source .upgrade-deps.sh

# run the tests
source .unittest.sh
