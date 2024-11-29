#!/bin/bash
# requires an activated venv
set -e

# lsh@2022-02-14: venv is now preserved by default
rm -f .no-delete-venv.flag

# python 3.8, 20.04
python=$(which python3.8 python3 | head -n 1)

py=${python##*/} # "python3.8"
echo "using $py"

if [ ! -e "venv/bin/$py" ]; then
    echo "could not find venv/bin/$py, recreating venv"
    rm -rf venv/*
fi

# create+activate venv
"$python" -m venv venv
source venv/bin/activate

pip install pip wheel --upgrade

# setup some paths correctly for pip to use the homebrew versions of libraries on macOS
if [ "$(uname -s)" == "Darwin" ] ; then
    export OPENSSL_ROOT_DIR="$(brew --prefix openssl@1.1)"
    export LDFLAGS="-L$(brew --prefix openssl@1.1)/lib -L$(brew --prefix libffi)/lib -L$(brew --prefix libssh2)/lib"
    export CPPFLAGS="-I$(brew --prefix openssl@1.1)/include -I$(brew --prefix libffi)/include -I$(brew --prefix libssh2)/include"

fi

pip install -r requirements.txt
