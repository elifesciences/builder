#!/bin/bash
# requires an activated venv
set -e

python=$(which python3 python | head -n 1)

py=${python##*/} # "python3" or "python"
echo "using binary $py ($python - $($py --version))"

if [[ "$(readlink venv/bin/$py)" != "$python"  ]]; then
    echo "venv/bin/$py is not symlinked to $python recreating venv"
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
