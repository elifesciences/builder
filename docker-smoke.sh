#!/bin/bash
set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: ./docker-smoke.sh PYTHON_MAJOR_VERSION"
    echo "Example: ./docker-smoke.sh 2"
    exit 1
fi

mkdir -p .cfn/stacks .cfn/keypairs .cfn/contexts .cfn/terraform logs
touch logs/app.log
if [ "$1" -eq 2 ]; then
    echo "Python 2 container smoke test"
    rm -f .use-python-3.flag
    ./python-docker.sh .project.py
elif [ "$1" -eq 3 ]; then
    echo "Python 3 container smoke test"
    touch .use-python-3.flag
    ./python-docker.sh .project.py
else
    echo "Unknown Python major version $1"
    exit 2
fi
