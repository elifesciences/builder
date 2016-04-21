#!/bin/bash
set -e
find . -name '*.pyc' -delete
pylint src/*.py src/buildercore/*.py --rcfile=.comprehensive-pylintrc
echo "* passed full lint!"
