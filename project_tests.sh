#!/bin/bash
set -e

. .activate-venv.sh
. .lint.sh
. .shell-lint.sh
. .run-tests.sh src/
#./full-lint.sh
