#!/bin/bash

set -e # everything must pass

# note: deliberately ignores integration tests!
pytest src/tests/ -vv "$@"
