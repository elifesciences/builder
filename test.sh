#!/bin/bash
# runs just the project tests,
# and optionally the integration tests with BUILDER_INTEGRATION_TESTS=1,
# with no linting or scrubbing.
# used in CI where linting/scrubbing/etc are separate steps.
set -e

. .activate-venv.sh
. .tests.sh
