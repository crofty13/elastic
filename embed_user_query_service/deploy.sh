#!/bin/bash
docker buildx build --platform linux/amd64,linux/arm64 -t embed-user-query-service:latest -t crofty1300/embed-user-query-service:latest --load .
kubectl apply -f deployment.yaml

