#!/bin/bash
set -e

source venv/bin/activate

. .scrub.sh 2> /dev/null
echo "Failing if scrub produces local modifications"
git diff --exit-code
