#!/bin/bash
docker build -f query_clothes_service/Dockerfile -t query-clothes-service:v1 query_clothes_service/
kubectl apply -f query_clothes_service/deployment.yaml

