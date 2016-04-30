#!/bin/bash 

# everything must pass
set -e

# recreate the virtualenv
rm -rf venv/
source .activate-venv.sh

# upgrade all deps to latest version
pip install pip-review
pip-review --pre # preview the upgrades
echo "[any key to continue ...]"
read -p "$*"
echo "updating ..."
pip-review --auto --pre # update everything
