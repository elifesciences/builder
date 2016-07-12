#!/bin/bash
# updates a formula on the master server

set -e # everything must pass
set -u # no unbound variables

pname=$1
formula=$2

mkdir -p /opt/formulas
if [ -d "/opt/formulas/$pname" ]; then
    cd /opt/formulas/$pname
    git reset --hard
    git pull
else
    cd /opt/formulas/
    git clone $formula $pname
fi
