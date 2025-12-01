#!/bin/bash
docker buildx build --platform linux/amd64,linux/arm64 -t main-service:latest -t crofty1300/main-service:latest --load .
kubectl apply -f deployment.yaml

