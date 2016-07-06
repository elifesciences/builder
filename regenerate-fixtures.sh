#!/bin/bash
set -e
source venv/bin/activate
./.project.py dummy1 --format json > src/tests/fixtures/dummy1-project.json
./.project.py dummy2 --format json > src/tests/fixtures/dummy2-project.json
./.project.py dummy3 --format json > src/tests/fixtures/dummy3-project.json
