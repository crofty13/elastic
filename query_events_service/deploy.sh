#!/bin/bash
docker build -f query_events_service/Dockerfile -t query-events-service:v1 query_events_service/
kubectl apply -f query_events_service/deployment.yaml

