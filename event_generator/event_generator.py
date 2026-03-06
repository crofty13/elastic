#!/usr/bin/env python3
"""
Event Generator Service

Generates new events for the chatbot app.
Uses OpenAI to create events based on UK happenings over the next 12 months,
then indexes them into Elasticsearch with embeddings. Same OTEL, logging, and
Elastic/OpenAI configuration as other services.
"""

import os
import sys
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

# Check for required modules
try:
    from flask import Flask, request, jsonify
    from elasticsearch import Elasticsearch
    from openai import OpenAI
except ImportError as e:
    print("ERROR|{\"message\": \"Required packages not found\", \"error\": \"" + str(e).replace('"', '\\"') + "\"}")
    sys.exit(1)

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Env checks
for var in ("ELASTIC_API_KEY", "ELASTIC_ENDPOINT", "OPENAI_API_KEY"):
    if not os.environ.get(var):
        print(f"ERROR|{{\"message\": \"{var} environment variable not set\"}}")
        sys.exit(1)

ELASTIC_ENDPOINT = os.environ["ELASTIC_ENDPOINT"].strip().rstrip("/")
INDEX_EVENTS = "events"
EVENTS_PER_RUN = 10

# Path to Elastic_indexes (in repo, copied into image)
SCRIPT_DIR = Path(__file__).resolve().parent
ELASTIC_INDEXES_DIR = os.environ.get("ELASTIC_INDEXES_DIR", str(SCRIPT_DIR / "Elastic_indexes"))

app = Flask(__name__)


# --- Logging (same pattern as query_events_service) ---
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        standard_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs", "message",
            "pathname", "process", "processName", "relativeCreated", "thread",
            "threadName", "exc_info", "exc_text", "stack_info",
        }
        for key, value in record.__dict__.items():
            if key not in standard_fields:
                log_data[key] = value
        json_str = json.dumps(log_data, ensure_ascii=False, default=str)
        return f"{record.levelname}|{json_str}"


def setup_logging():
    logger = logging.getLogger("event_generator")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    formatter = JSONFormatter()
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(lambda r: r.levelno <= logging.INFO)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)
    return logger


logger = setup_logging()


# --- Load Elastic index docs into variables ---
def load_elastic_index_docs():
    """Load put-events+embeddings.md and put-clothese.md into variables."""
    events_md = clothes_md = None
    events_path = Path(ELASTIC_INDEXES_DIR) / "put-events+embeddings.md"
    clothes_path = Path(ELASTIC_INDEXES_DIR) / "put-clothese.md"
    if events_path.exists():
        events_md = events_path.read_text(encoding="utf-8")
    else:
        logger.warning("Elastic_indexes/put-events+embeddings.md not found", extra={"path": str(events_path)})
    if clothes_path.exists():
        clothes_md = clothes_path.read_text(encoding="utf-8")
    else:
        logger.warning("Elastic_indexes/put-clothese.md not found", extra={"path": str(clothes_path)})
    return {"events_schema": events_md, "clothes_schema": clothes_md}


# --- OpenTelemetry ---
def setup_opentelemetry():
    if not OTEL_AVAILABLE:
        return
    try:
        api_key = (os.environ.get("ELASTIC_API_KEY") or "").strip()
        if not api_key or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            return
        os.environ.setdefault("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=ApiKey {api_key}")
        if not os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
                "service.name=event-generator,service.version=1,deployment.environment=production"
            )
        resource_attrs = {}
        for attr in (os.environ.get("OTEL_RESOURCE_ATTRIBUTES") or "").split(","):
            if "=" in attr:
                k, v = attr.split("=", 1)
                resource_attrs[k.strip()] = v.strip()
        resource = Resource.create(resource_attrs)
        tracer_provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
            headers={"Authorization": f"ApiKey {api_key}"},
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(tracer_provider)
        FlaskInstrumentor().instrument_app(app)
        OpenAIInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        logger.info("OpenTelemetry instrumentation enabled")
    except Exception as e:
        logger.warning("OpenTelemetry setup failed: %s", e)


def get_elasticsearch_client():
    api_key = (os.environ.get("ELASTIC_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("ELASTIC_API_KEY not set")
    # Longer timeout for index: default pipeline runs inference (embedding) and can take 30–60s per doc
    return Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key, request_timeout=120)


def get_openai_client():
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


def fetch_existing_events_names_descriptions(es):
    """
    GET from Elasticsearch events index: retrieve name and description only from all documents.
    Returns a list of dicts [{"name": "...", "description": "..."}, ...] for use in the prompt.
    """
    try:
        res = es.search(
            index=INDEX_EVENTS,
            body={
                "size": 1000,
                "_source": ["name", "description"],
                "query": {"match_all": {}},
            },
            request_timeout=30,
        )
        hits = res.get("hits", {}).get("hits", [])
        existing = []
        for h in hits:
            src = h.get("_source") or {}
            existing.append({
                "name": src.get("name") or "",
                "description": (src.get("description") or "")[:500],
            })
        return existing
    except Exception as e:
        logger.warning("Failed to fetch existing events from Elasticsearch: %s", e)
        return []


# Normalize constrained fields to lowercase keyword form
SEASONS = {"summer", "spring", "autumn", "winter"}
FORMALITY = {"formal", "smart-casual", "casual"}
TYPE_VALS = {"outdoor", "indoor"}


def normalize_event(doc):
    if doc.get("season"):
        s = str(doc["season"]).strip().lower()
        if s in SEASONS:
            doc["season"] = s
        else:
            doc["season"] = "summer"
    if doc.get("formality"):
        f = str(doc["formality"]).strip().lower()
        if f in FORMALITY:
            doc["formality"] = f
        else:
            doc["formality"] = "casual"
    if doc.get("type"):
        t = str(doc["type"]).strip().lower()
        if t in TYPE_VALS:
            doc["type"] = t
        else:
            doc["type"] = "indoor"
    return doc


def generate_one_event(openai_client, events_schema, existing_events_text):
    """
    Ask OpenAI for one new real UK event. Uses existing_events_text so the model creates events
    that are new and different. Returns a dict suitable for events index.
    """
    system = (
        "You are an event generator for a fashion/events app. You output only valid JSON, no markdown or explanation. "
        "Generate one REAL event that is happening or will happen in the UK over the next 12 months. "
        "Examples of the kind of real events to use: sports events (e.g. Wimbledon, Six Nations, British Grand Prix), "
        "celebrity weddings, outdoor BBQ or garden parties, garden fairs, festivals, royal or public occasions, "
        "races (e.g. London Marathon), concerts, food and drink events, country shows. "
        "Do NOT make up fictional events; base events on real or plausible real UK happenings. "
        "Use the exact structure and field names from the events index schema below. "
        "Required constrained fields: "
        "season must be exactly one of: Summer, Spring, Autumn, Winter; "
        "formality must be exactly one of: formal, smart-casual, casual; "
        "type must be exactly one of: outdoor, indoor. "
        "Include: event_id (e.g. evt_002), name, occasion, season, formality, type, location, description, dos, donts, "
        "fashion_trends_women (current_trends, recommended_accessories), fashion_trends_men (same), "
        "ideal_outfit_tags (women: occasion, season, formality; men: same). "
        "image_url can be a placeholder. Return only the JSON object."
    )
    user_parts = []
    if existing_events_text.strip():
        user_parts.append(
            "EXISTING EVENTS ALREADY IN THE STORE (create NEW events that are different from these; do not duplicate):\n"
            + existing_events_text.strip()
            + "\n\n"
        )
    user_parts.append(
        "Using this Elasticsearch events index schema and example, generate one new unique REAL UK event as a single JSON object.\n\n"
        + (events_schema or "No schema loaded.")
    )
    user = "".join(user_parts)
    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.9,
    )
    text = (resp.choices[0].message.content or "").strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("OpenAI returned invalid JSON: %s", e, extra={"raw_preview": text[:200]})
        raise ValueError("OpenAI response was not valid JSON") from e
    return normalize_event(doc)


def index_event(es, doc):
    """Index one event document into Elasticsearch events index. Embedding is added by the index default pipeline."""
    event_id = doc.get("event_id") or ("evt_" + uuid.uuid4().hex[:8])
    # Ensure "name" appears before "event_id"; drop embedding fields (pipeline will add embedding)
    name = doc.get("name") or ""
    body = {"name": name, "event_id": event_id}
    for key, value in doc.items():
        if key in ("embedding", "embedding_model"):
            continue
        if key not in body:
            body[key] = value
    body["event_id"] = event_id
    return es.index(index=INDEX_EVENTS, id=event_id, body=body, request_timeout=120)


# --- API routes ---
@app.route("/", methods=["GET"])
def index():
    """Service info and usage."""
    return jsonify({
        "service": "event-generator",
        "description": "Generate events for the chatbot app; stores in Elasticsearch.",
        "endpoints": [
            "GET  /         - this info",
            "GET  /health   - health check",
            "POST /generate - generate N events (default 10), optional body: {\"count\": N}",
        ],
        "events_per_run_default": EVENTS_PER_RUN,
    }), 200


@app.route("/health", methods=["GET"])
def health_check():
    try:
        es = get_elasticsearch_client()
        es.info()
        return jsonify({"status": "healthy", "service": "event-generator", "elasticsearch": {"connected": True}}), 200
    except Exception as e:
        logger.error("Health check failed: %s", e, exc_info=True)
        return jsonify({
            "status": "degraded",
            "service": "event-generator",
            "elasticsearch": {"connected": False},
            "error": str(e),
        }), 200


@app.route("/generate", methods=["POST"])
def generate_events():
    """
    Generate N new events (default 10), store in Elasticsearch events index.
    Optional JSON body: { "count": 10 } to override number of events.
    """
    try:
        count = EVENTS_PER_RUN
        if request.is_json:
            data = request.get_json() or {}
            count = int(data.get("count", EVENTS_PER_RUN))
        count = max(1, min(count, 50))

        index_docs = load_elastic_index_docs()
        events_schema = index_docs.get("events_schema")
        if not events_schema:
            return jsonify({"error": "Elastic_indexes/put-events+embeddings.md not found", "status": "error"}), 500

        openai_client = get_openai_client()
        es = get_elasticsearch_client()

        created = []
        for i in range(count):
            # Fetch existing events on each loop so the list is up to date (includes just-indexed events)
            existing_events = fetch_existing_events_names_descriptions(es)
            existing_events_text = "\n".join(
                f"- Name: {e['name']}\n  Description: {e['description']}"
                for e in existing_events
            )
            if existing_events_text and i == 0:
                logger.info("Loaded %s existing events for prompt", len(existing_events), extra={"existing_count": len(existing_events)})

            logger.info("Generating event %s/%s", i + 1, count)
            event_doc = generate_one_event(openai_client, events_schema, existing_events_text)
            # Ensure unique event_id so we create N distinct documents (OpenAI often repeats evt_002)
            event_doc["event_id"] = f"evt_gen_{uuid.uuid4().hex[:8]}"
            result = index_event(es, event_doc)
            created.append({"event_id": event_doc["event_id"], "_id": result.get("_id"), "result": result.get("result")})
            logger.info("Indexed event", extra={"event_id": event_doc["event_id"], "_id": result.get("_id")})

        return jsonify({
            "status": "success",
            "message": f"Generated and indexed {len(created)} events",
            "created": created,
        }), 200
    except ValueError as e:
        logger.warning("Generate validation error: %s", e)
        return jsonify({"error": str(e), "status": "error"}), 400
    except Exception as e:
        logger.error("Generate failed: %s", e, exc_info=True)
        return jsonify({"error": str(e), "status": "error"}), 500


if __name__ == "__main__":
    setup_opentelemetry()
    logger.info("Event generator service starting", extra={"elastic_indexes_dir": ELASTIC_INDEXES_DIR})
    app.run(host="0.0.0.0", port=5005, debug=False)
