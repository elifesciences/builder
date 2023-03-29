#!/bin/bash
# installs 'tfenv', a Terraform version manager: https://github.com/tfutils/tfenv
# this allows us to migrate projects between versions of Terraform.

set -e

if [ ! -d .tfenv ]; then
    wget https://github.com/tfutils/tfenv/archive/refs/tags/v3.0.0.tar.gz \
        --output-document=tfenv.tar.gz \
        --quiet
    sha256sum --check tfenv.sha256
    tar -xzf tfenv.tar.gz
    mv tfenv-3.0.0 .tfenv
    rm tfenv.tar.gz
fi

.tfenv/bin/tfenv install 0.11.15 # current, default, version
.tfenv/bin/tfenv install 0.13.7  # next version

# activate the default version.
# this is used when not overridden by ".terraform-version" or "TFENV_TERRAFORM_VERSION"
.tfenv/bin/tfenv use 0.11.15
