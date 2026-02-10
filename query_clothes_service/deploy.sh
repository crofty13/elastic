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
docker buildx build --platform $PLATFORM -f "$SCRIPT_DIR/Dockerfile" -t query-clothes-service:v2 "$SCRIPT_DIR" --load

kubectl apply -f "$SCRIPT_DIR/deployment.yaml"
kubectl rollout status deployment query-clothes-service --timeout=120s
