#!/bin/bash
set -e

echo "[-] .lint.sh"

echo "scrubbing"
. .scrub.sh

echo "pyflakes"
.ci/pyflakes

echo "pylint"
.ci/pylint

echo "[✓] .lint.sh"
