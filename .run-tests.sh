#!/bin/bash
# ignores integration tests.
# see `.run-tests-ci.sh` for running the integration testing.
# called by `test.sh` and `canary.sh`
set -e
args="$@"

# skip utils.confirm() prompts during testing
export BUILDER_NON_INTERACTIVE=1

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.
# see `venv/bin/pytest` and `src/buildercore/threadbare/__init__.py`

if [ -z "$args" ]; then
    # no arguments given, run the regular test suite and ignore integration tests
    ./patched_pytest src/tests/ -vv
else
    ./patched_pytest -vv "$@"
fi
