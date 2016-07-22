#!/bin/bash
set -e # causes script to exit immediately on error

. .activate-venv.sh
. .lint.sh
. .shell-lint.sh
. .unittest.sh
#./full-lint.sh
