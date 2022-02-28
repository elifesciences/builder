#!/bin/bash
set -e

# lsh@2022-02-14: threadbare is now the default backend. flag switched to '.use-fabric.flag'
rm -f .use-threadbare.flag

# lsh@2022-02-14: venv is now preserved by default
rm -f .no-delete-venv.flag

# lsh@2022-02-14: python2 support has been removed
rm -f .use-python-3.flag
# python 3.6, 18.04
# python 3.8, 20.04
python=$(which python3.8 python3.6 python3 | head -n 1)

py=${python##*/} # "python3.6"
echo "using $py"

if [ ! -e "venv/bin/$py" ]; then
    echo "could not find venv/bin/$py, recreating venv"
    rm -rf venv
fi

# create+activate venv
"$python" -m venv venv
source venv/bin/activate

pip install pip wheel --upgrade
pip install -r requirements.txt
