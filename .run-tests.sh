#!/bin/bash
# ignores integration tests.
# see `.run-tests-ci.sh` for running the integration testing.
# called by `test.sh` and `canary.sh`

set -e

# `patched_pytest` is a copy of 'pytest' but with gevent monkey patching.
# see `venv/bin/pytest` and `src/buildercore/threadbare/__init__.py`
./patched_pytest -vv "$@"
