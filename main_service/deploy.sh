#!/bin/bash
docker build -f main_service/Dockerfile -t main-service:v3 main_service/
kubectl apply -f main_service/deployment.yaml
kubectl rollout restart deployment main-service

