#!/bin/bash
set -e

echo "[-] .lint.sh"

# remove any old compiled python files
# pylint likes to lint them
find src/ -name '*.py[c|~]' -delete
find src/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

echo "pyflakes"
# this skips the fabfile.py file, which pyflakes complains about endlessly
# also skips complains about 'raw_input' and 'file' not being defined in python3
if pyflakes src/ | grep -v -E "src/fabfile.py|'raw_input'|'file'"; then exit 1; fi

echo "pylint"
# E1129=doesn't like Fabric's context manager
# E1101=no-member, temporary while python2 is still supported
# E0602=undefined-variable, temporary while python2 is still supported
pylint -E *.py ./src/*.py src/buildercore/*.py src/buildercore/project/*.py src/tests/*.py src/integration_tests/*.py \
    --disable=E1129 \
    --disable=E1101 \
    --disable=E0602 2> /dev/null
# specific warnings we're interested in, comma separated with no spaces
# presence of these warnings are a failure
# TODO: re-add 'redefined-builtin' after python2 support dropped
pylint *.py ./src/*.py src/buildercore/*.py src/buildercore/project/*.py \
    --disable=all --reports=n --score=n \
    --enable=pointless-string-statement,no-else-return,redefined-outer-name 2> /dev/null

echo "scrubbing"
. .scrub.sh 2> /dev/null

echo "[✓] .lint.sh"
