#!/bin/bash
set -e

echo "[-] .lint.sh"

# remove any old compiled python files
# pylint likes to lint them
find src/ -name '*.py[c|~]' -delete
find src/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

echo "pyflakes"
# this skips the fabfile.py file, which pyflakes complains about endlessly
if pyflakes src/ | grep -v src/fabfile.py; then exit 1; fi

echo "pylint"
# E1129=doesn't like Fabric's context manager
pylint -E *.py ./src/*.py src/buildercore/*.py src/buildercore/project/*.py src/tests/*.py \
    --disable=E1129 2> /dev/null
# specific warnings we're interested in, comma separated with no spaces
# presence of these warnings are a failure
pylint *.py ./src/*.py src/buildercore/*.py src/buildercore/project/*.py \
    --disable=all --reports=n --score=n \
    --enable=redefined-builtin 2> /dev/null

echo "scrubbing"
. .scrub.sh 2> /dev/null

echo "[✓] .lint.sh"
