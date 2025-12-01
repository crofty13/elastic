#!/bin/bash
docker buildx build --platform linux/amd64,linux/arm64 -t query-clothes-service:latest -t crofty1300/query-clothes-service:latest --load .
kubectl apply -f deployment.yaml

