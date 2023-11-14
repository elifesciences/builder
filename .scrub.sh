#!/bin/bash
# scrub.sh uses ruff to fix any small bits
# requires an activated venv

ruff check \
    --config .ruff.toml \
    --fix-only \
    --unsafe-fixes \
    *.py src/
