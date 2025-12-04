#!/bin/bash

# Get current user's UID and GID
USER_UID=$(id -u)
USER_GID=$(id -g)

echo "Building gofr-dig_dev with USER_UID=$USER_UID and USER_GID=$USER_GID"

docker build \
--build-arg USER_UID=$USER_UID \
--build-arg USER_GID=$USER_GID \
-f docker/Dockerfile.dev \
-t gofr-dig_dev:latest \
.