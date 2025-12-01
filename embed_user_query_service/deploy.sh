#!/bin/bash
docker build -f embed_user_query_service/Dockerfile -t embed-user-query-service:v1 embed_user_query_service/
kubectl apply -f embed_user_query_service/deployment.yaml

