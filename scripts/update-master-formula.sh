#!/bin/bash
# updates a formula on a masterless or master server

set -e # everything must pass
set -u # no unbound variables

pname=$1
formula=$2
revision=${3:-""}

formula_root="/opt/formulas"
if [ "$pname" == "builder-private" ]; then
    formula_root="/opt"
fi
formula_path="$formula_root/$pname"

mkdir -p "$formula_root"

if [ -d "$formula_path" ]; then
    cd "$formula_path"
    git reset --hard
    git clean -d --force
    git pull --rebase
else
    cd "$formula_root"
    git clone "$formula" "$pname"
fi

cd "$formula_path"

if [ "$revision" != "" ]; then
    git checkout "$revision"
fi
