#!/bin/bash
set -e

mkdir -p .cfn/stacks .cfn/keypairs .cfn/contexts .cfn/terraform logs
touch logs/app.log
echo "Python 3 container smoke test"
./python-docker.sh .project.py
