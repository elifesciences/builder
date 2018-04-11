#!/bin/bash

set -e # everything must pass

envname="${1:-default}"

export PYTHONPATH="src"
coverage run -m pytest \
    --cov=src \
    -s \
    --junitxml=build/pytest-$envname.xml \
    src/tests src/integration_tests

coverage report --fail-under=67
