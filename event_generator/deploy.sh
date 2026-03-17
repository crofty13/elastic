#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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
docker buildx build --platform "$PLATFORM" -f "$SCRIPT_DIR/Dockerfile" -t event-generator:latest "$SCRIPT_DIR" --load

kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
kubectl rollout status deployment/event-generator -n default --timeout=120s
