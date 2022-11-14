#!/bin/bash
set -e

echo "[-] .lint.sh"

echo "pyflakes"
.ci/pyflakes

echo "scrubbing"
. .scrub.sh

echo "pylint"
.ci/pylint

echo "[✓] .lint.sh"
