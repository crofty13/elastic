#!/bin/bash
docker buildx build --platform linux/amd64,linux/arm64 -t query-events-service:latest -t crofty1300/query-events-service:latest --load .
kubectl apply -f deployment.yaml

