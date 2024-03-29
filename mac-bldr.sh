#!/bin/bash
set -e

CUR_DIR=$(pwd)
TAG="${TAG:-local}"
CUSTOM_SSH_KEY="${CUSTOM_SSH_KEY-$HOME/.ssh/id_rsa}"
CUSTOM_AWS_CREDENTIALS="${CUSTOM_AWS_CREDENTIALS-$HOME/.aws/credentials}"

DOCKER=$(command -v docker || true)
if [ -z "$DOCKER" ]; then
    echo "$0: ERROR: unable to locate Docker! Have you got Docker installed?"
    exit 1
fi

if [ ! -f "$CUSTOM_SSH_KEY" ] || [ ! -f "$CUSTOM_SSH_KEY.pub" ]; then
    echo "$0: ERROR: $CUSTOM_SSH_KEY is not a valid path or file!"
    exit 1
fi

if [ ! -f "$CUSTOM_AWS_CREDENTIALS" ]; then
    echo "$0: ERROR: $CUSTOM_AWS_CREDENTIALS is not a path or file!"
    exit 1
fi

echo "$0: INFO: building container 'builder:${TAG}'"
$DOCKER build \
    -f "Dockerfile.osx" \
    -t "builder:${TAG}" \
    --platform linux/amd64 \
    .

echo "$0: INFO: starting container 'builder:${TAG}'"
$DOCKER run \
    --rm \
    --platform linux/amd64 \
    -it \
    -e "TZ=Europe/London" \
    -v "/etc/timezone:/etc/timezone:ro" \
    -v "/etc/localtime:/etc/localtime:ro" \
    -v "$CUSTOM_SSH_KEY:/root/.ssh/id_rsa:ro" \
    -v "$CUSTOM_SSH_KEY.pub:/root/.ssh/id_rsa.pub:ro" \
    -v "$CUSTOM_AWS_CREDENTIALS:/root/.aws/credentials:ro" \
    -v "$CUR_DIR:/builder:rw" \
    "builder:${TAG}"
