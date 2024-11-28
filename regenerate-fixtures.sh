#!/bin/bash
set -e
. venv/bin/activate
USER_SETTINGS_PATH=settings.fixtures.yaml PROJECT=dummy1 ./bldr project.data:output_format=json > src/tests/fixtures/dummy1-project.json
USER_SETTINGS_PATH=settings.fixtures.yaml PROJECT=dummy2 ./bldr project.data:output_format=json > src/tests/fixtures/dummy2-project.json
USER_SETTINGS_PATH=settings.fixtures.yaml PROJECT=dummy3 ./bldr project.data:output_format=json > src/tests/fixtures/dummy3-project.json
