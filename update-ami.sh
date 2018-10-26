#!/bin/bash
set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: ./update-ami.sh RELEASE AMI_ID"
    echo "Example: ./update-ami.sh 1804 ami-089646d3d52f14f1f"
    exit 1
fi

release="$1"
ami_id="$2"

sed -i -e "s/ami: .* # GENERATED created from basebox--${release}/ami: $ami_id # GENERATED created from basebox--${release}/g" projects/elife.yaml
