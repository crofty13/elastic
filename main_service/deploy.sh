#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Detect local architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "x86_64" ]] || [[ "$ARCH" == "amd64" ]]; then
    PLATFORM="linux/amd64"
elif [[ "$ARCH" == "arm64" ]] || [[ "$ARCH" == "aarch64" ]]; then
    PLATFORM="linux/arm64"
else
    echo "ERROR: Unsupported architecture: $ARCH"
    exit 1
fi

echo "Building for local architecture: $PLATFORM"
# Build for local architecture only
docker buildx build --platform $PLATFORM -f "$SCRIPT_DIR/Dockerfile" -t main-service:v3 "$SCRIPT_DIR" --load

kubectl rollout restart deployment main-service

