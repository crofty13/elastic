# Event Generator Service

Generates new **events** for the chatbot app. Uses OpenAI to create events based on real UK happenings over the next 12 months, then indexes them into the Elasticsearch **events** index (embedding added by index pipeline).

- Same **OTEL**, **logging**, and **Elastic/OpenAI** configuration as other services.
- Loads index schemas from `Elastic_indexes/` (put-events+embeddings.md, put-clothese.md).
- Constrained fields: **season** (Summer, Spring, Autumn, Winter), **formality** (formal, smart-casual, casual), **type** (outdoor, indoor).

## Endpoints

- `GET /` – Service info and usage.
- `GET /health` – Health check (returns 200; body indicates ES connectivity).
- `POST /generate` – Generate and index events. Optional body: `{"count": 10}` (default 10, max 50).

## Run locally

```bash
# From repo root, with env loaded
source keys.sh
export ELASTIC_INDEXES_DIR="$(pwd)/data-generator/Elastic_indexes"
python data-generator/event_generator.py
# Then: curl -X POST http://localhost:5005/generate
```

## Deploy (Kubernetes)

Requires secrets: `elastic-api-key`, `elastic-endpoint`, `openai-api-key`, `otel-exporter-otlp-endpoint`.

```bash
./data-generator/deploy.sh
# Trigger generation (e.g. from a job or manually):
kubectl run curl --rm -it --restart=Never --image=curlimages/curl -- curl -s -X POST http://event-generator:5005/generate
```

## Environment

- `ELASTIC_API_KEY`, `ELASTIC_ENDPOINT` – Elasticsearch.
- `OPENAI_API_KEY` – OpenAI (events generation).
- `OTEL_EXPORTER_OTLP_ENDPOINT` – OpenTelemetry (optional).
- `ELASTIC_INDEXES_DIR` – Path to `Elastic_indexes` (default: `/app/Elastic_indexes` in container).
