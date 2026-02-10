# Elastic Search Project

This project contains Python scripts for working with Elasticsearch and OpenAI embeddings.
This only works on full Elastic Cloud and self managed. the Serverless version doesnt work.

## Setup

### 1. Set Environment Variables

Before running any scripts, you need to source the environment variables from `keys.sh`:
You will need an Elastic key and an OpenAI key in a file which is sources. 


```bash
source keys.sh
```

This will set the following environment variables:
- `OPENAI_API_KEY` - Your OpenAI API key
- `ELASTIC_API_KEY` - Your Elasticsearch API key
-  `ELASTIC_ENDPOINT` - Your Elastic Cloud Search endpoint
-  `OTEL_EXPORTER_OTLP_ENDPOINT`= Elastic Cloud Observabillity endpoint (/v1/traces)


**Important:** The `keys.sh` file contains sensitive API keys and is excluded from git via `.gitignore`. Never commit this file.

### 2. Add these are keys to kubernetes
```
kubectl create secret generic elastic-api-key  --from-literal=apiKey="$ELASTIC_API_KEY"
kubectl create secret generic openai-api-key --from-literal=apiKey="$OPEN_API_KEY"
kubectl create secret generic otel-exporter-otlp-endpoint --from-literal=endpoint="$OTEL_EXPORTER_OTLP_ENDPOINT"
kubectl create secret generic elastic-endpoint --from-literal=endpoint="$ELASTIC_ENDPOINT"
```

### 3. Create the to indexes and embeddings that you will need.
go to Elastic_indexes
run all the commands in those two files in Elastic.


### 4.
create random product descriptions in the index
create raandom events descriptions in the index.

### 5.
spin up the docker builds. (deploy.sh should be fixed)

### 6.
think about how to create new events from an an agent.




user create the embeddings
