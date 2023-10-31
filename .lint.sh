#!/bin/bash
set -e

ruff check \
    --config .ruff.toml \
    *.py src/
