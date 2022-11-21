#!/bin/bash
set -e

echo "[-] .lint.sh"

echo "pyflakes"
.ci/pyflakes

echo "pylint"
.ci/pylint

echo "scrubbing"
. .scrub.sh

echo "[✓] .lint.sh"
