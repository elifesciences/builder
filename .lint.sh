#!/bin/bash
set -e

echo "pyflakes"
.ci/pyflakes

echo "pylint"
.ci/pylint

echo "scrubbing"
. .scrub.sh
