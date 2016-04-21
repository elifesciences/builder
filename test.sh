#!/bin/bash
set -e # causes script to exit immediately on error

source .activate-venv.sh
source .lint.sh
source .unittest.sh
source .full-lint.sh
