# Upload Events to Elastic - Kubernetes Deployment

This directory contains the Kubernetes deployment files for the upload events Flask API.

## Prerequisites

- Kubernetes cluster
- kubectl configured
- Docker (for building the image)
- Docker buildx (for multi-architecture builds)
- Docker registry (or use a local registry)

## Quick Start

### 1. Build the Docker Image

#### Set up Docker buildx (first time only)

```bash
# Create and use a new buildx builder instance
docker buildx create --name multiarch --use

# Verify it supports multiple platforms
docker buildx inspect --bootstrap
```

#### Build for multiple architectures (x86 and ARM)

```bash
# Build for both linux/amd64 (x86) and linux/arm64 (ARM/Apple Silicon)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t upload-events-to-elastic:latest \
  --push \
  .

# If using a remote registry, build and push directly:
# docker buildx build \
#   --platform linux/amd64,linux/arm64 \
#   -t your-registry/upload-events-to-elastic:latest \
#   --push \
#   .
```

**Note:** The `--load` flag loads the image into the local Docker daemon. If you're building for a different architecture than your current machine (e.g., building ARM on x86), you may need to use `--push` instead and push to a registry, then pull it back.

#### Build for your current architecture only (faster, for local testing)

```bash
# Build for your current architecture
docker build -t upload-events-to-elastic:latest .
```

### 2. Verify the Secret Exists

The deployment references an existing secret named `elastic-api-key` with key `apiKey`. 

Ensure this secret exists in your cluster:

```bash
# Check if the secret exists
kubectl get secret elastic-api-key

# If it doesn't exist, create it:
# kubectl create secret generic elastic-api-key \
#   --from-literal=apiKey=your-actual-api-key-here
```

### 3. Update the Image in deployment.yaml

If you're using a remote registry, update the image name in `deployment.yaml`:

```yaml
image: your-registry/upload-events-to-elastic:latest
```

### 4. Deploy to Kubernetes

```bash
kubectl apply -f deployment.yaml
```

### 5. Check Deployment Status

```bash
# Check pods
kubectl get pods -l app=upload-events-to-elastic

# Check services
kubectl get svc -l app=upload-events-to-elastic

# Check logs
kubectl logs -l app=upload-events-to-elastic
```

### 6. Access the Service

The deployment creates two services:

1. **LoadBalancer Service** (port 80 → 5001)
   - Get external IP: `kubectl get svc upload-events-to-elastic-service`
   - Access at: `http://<EXTERNAL-IP>/upload`

2. **NodePort Service** (port 30081)
   - Access at: `http://<NODE-IP>:30081/upload`
   - Get node IP: `kubectl get nodes -o wide`

## Testing the API

Once deployed, test the health endpoint:

```bash
# Using LoadBalancer
curl http://<EXTERNAL-IP>/health

# Using NodePort
curl http://<NODE-IP>:30081/health
```

Upload an event:

```bash
curl -X POST http://<EXTERNAL-IP>/upload \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Event",
    "type": "sporting_event",
    ...
  }'
```

## Updating the Deployment

After making changes to the code:

```bash
# Rebuild the multi-architecture image
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t upload-events-to-elastic:latest \
  --load \
  .

# If using a remote registry:
# docker buildx build \
#   --platform linux/amd64,linux/arm64 \
#   -t your-registry/upload-events-to-elastic:latest \
#   --push \
#   .

# Restart the deployment
kubectl rollout restart deployment/upload-events-to-elastic
```

## Scaling

Scale the deployment:

```bash
kubectl scale deployment upload-events-to-elastic --replicas=3
```

## Troubleshooting

- **Pods not starting**: Check logs with `kubectl logs <pod-name>`
- **Service not accessible**: Verify LoadBalancer has an external IP or use NodePort
- **API key issues**: Verify secret exists: `kubectl get secret elastic-api-key`
- **Image pull errors**: Ensure image is accessible from your cluster

