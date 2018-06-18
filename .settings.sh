#!/bin/bash

# generate a settings file if one doesn't exist
if [ ! -e settings.yml ]; then
    echo "* settings.yml not found, creating"
    grep -Ev '\w*##' example.settings.yml > settings.yml
fi
