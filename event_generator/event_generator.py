#!/usr/bin/env python3
"""
Event Generator Service

Generates new events for the chatbot app, and for each event generates 3 clothing
items (top, bottom, shoes) appropriate for that event. Uses OpenAI for both;
events go to the Elasticsearch events index (with embeddings), clothes to the
clothes index. Same OTEL, logging, and Elastic/OpenAI configuration as other services.
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
INDEX_CLOTHES = "clothes"
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


def fetch_existing_clothes_names_descriptions(es):
    """
    Fetch name and description of every document in the clothes index.
    Returns a list of dicts [{"name": "...", "description": "..."}, ...] for the prompt.
    Description truncated to 500 chars to match existing clothes generator limits.
    """
    try:
        res = es.search(
            index=INDEX_CLOTHES,
            body={
                "size": 10000,
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
        logger.warning("Failed to fetch existing clothes from Elasticsearch: %s", e)
        return []


def generate_three_clothes_for_event(openai_client, clothes_schema, event, existing_clothes_text):
    """
    Ask OpenAI for 3 clothing items (top, bottom, shoes) appropriate for the given event.
    season and occation must match the event. Returns a list of 3 dicts suitable for the clothes index.
    Uses existing_clothes_text to avoid duplicating names/descriptions.
    Event description limited to 800 chars in prompt (same as clothes generator).
    """
    event_name = event.get("name") or "Unknown event"
    occasion = event.get("occasion") or "casual"
    season = event.get("season") or "summer"
    description = (event.get("description") or "")[:800]

    system = (
        "You are a fashion generator for a clothing app. You output only valid JSON, no markdown or explanation. "
        "Generate exactly 3 fake clothing items that would be appropriate to wear to the given event. "
        "The 3 items must be: "
        "1) A TOP (e.g. jumper, dress, t-shirt, blouse, shirt, sweater). "
        "2) A BOTTOM (e.g. trousers, skirt, shorts, jeans, chinos). "
        "3) SHOES (e.g. loafers, trainers, boots, heels, sandals). "
        "Use the exact field names from the clothes index schema: name, description, body, occation, price, season, sex. "
        "Set 'body' to exactly one of: 'top', 'bottom', 'shoes' for each item. "
        "Set 'occation' and 'season' to match the event exactly (occation: " + repr(occasion) + ", season: " + repr(season) + "). "
        "Use 'sex' as 'unisex' or 'men' or 'women'. "
        "Price can be a string like '£45' or '£120'. "
        "Descriptions should be 1–2 sentences, fake product copy. "
        "Return a JSON object with a single key 'items' whose value is an array of exactly 3 objects, one for top, one for bottom, one for shoes. "
        "Do NOT duplicate or closely mimic any name or description from the EXISTING CLOTHES list provided; create new fake items."
    )
    user_parts = []
    if existing_clothes_text.strip():
        user_parts.append(
            "EXISTING CLOTHES ALREADY IN THE STORE (do not duplicate these names or descriptions):\n"
            + existing_clothes_text.strip()
            + "\n\n"
        )
    user_parts.append(
        "Event: " + event_name + "\n"
        "Occasion: " + str(occasion) + ", Season: " + str(season) + "\n"
        "Event description: " + description + "\n\n"
        "Clothes index schema:\n" + (clothes_schema or "No schema.")
        + "\n\nGenerate exactly 3 new unique clothing items (one top, one bottom, one shoes) as a single JSON object: {\"items\": [ {...}, {...}, {...} ]}."
    )
    user = "".join(user_parts)

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.8,
    )
    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("OpenAI returned invalid JSON: %s", e, extra={"raw_preview": text[:300]})
        raise ValueError("OpenAI response was not valid JSON") from e

    items = data.get("items")
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError("OpenAI must return {\"items\": [top, bottom, shoes]} with exactly 3 objects")

    for i, obj in enumerate(items):
        if not isinstance(obj, dict):
            raise ValueError("Each item must be a JSON object")
        obj.setdefault("body", ["top", "bottom", "shoes"][i])
        obj["occation"] = occasion
        obj["season"] = season
    return items


def index_clothes_doc(es, doc):
    """Index one clothing document into the clothes index. Returns index result."""
    doc_id = "cloth_" + uuid.uuid4().hex[:12]
    return es.index(index=INDEX_CLOTHES, id=doc_id, body=doc, request_timeout=30)


# --- API routes ---
@app.route("/", methods=["GET"])
def index():
    """Service info and usage."""
    return jsonify({
        "service": "event-generator",
        "description": "Generate events and 3 clothes per event; stores in Elasticsearch (events + clothes indices).",
        "endpoints": [
            "GET  /         - this info",
            "GET  /health   - health check",
            "POST /generate - generate N events (default 10), each with 3 clothing items; optional body: {\"count\": N}",
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
    Generate N new events (default 10), each with 3 clothing items (top, bottom, shoes).
    Events stored in Elasticsearch events index; clothes in clothes index. Optional body: { "count": N }.
    """
    try:
        count = EVENTS_PER_RUN
        if request.is_json:
            data = request.get_json() or {}
            count = int(data.get("count", EVENTS_PER_RUN))
        count = max(1, min(count, 50))

        index_docs = load_elastic_index_docs()
        events_schema = index_docs.get("events_schema")
        clothes_schema = index_docs.get("clothes_schema")
        if not events_schema:
            return jsonify({"error": "Elastic_indexes/put-events+embeddings.md not found", "status": "error"}), 500
        if not clothes_schema:
            return jsonify({"error": "Elastic_indexes/put-clothese.md not found", "status": "error"}), 500

        openai_client = get_openai_client()
        es = get_elasticsearch_client()

        created_events = []
        created_clothes = []
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
            created_events.append({"event_id": event_doc["event_id"], "_id": result.get("_id"), "result": result.get("result")})
            logger.info("Indexed event", extra={"event_id": event_doc["event_id"], "_id": result.get("_id")})

            # Generate 3 clothes for this event: fetch existing clothes, call OpenAI, index to clothes
            existing_clothes = fetch_existing_clothes_names_descriptions(es)
            existing_clothes_text = "\n".join(
                f"- Name: {c['name']}\n  Description: {c['description']}"
                for c in existing_clothes
            )
            try:
                items = generate_three_clothes_for_event(
                    openai_client, clothes_schema, event_doc, existing_clothes_text
                )
                for item in items:
                    clothes_result = index_clothes_doc(es, item)
                    created_clothes.append({
                        "event_id": event_doc["event_id"],
                        "body": item.get("body"),
                        "item_name": item.get("name"),
                        "_id": clothes_result.get("_id"),
                    })
                    logger.info(
                        "Indexed clothes",
                        extra={"item_name": item.get("name"), "body": item.get("body"), "_id": clothes_result.get("_id")},
                    )
            except ValueError as e:
                logger.warning("Skipping clothes for event %s: %s", event_doc.get("event_id"), e)

        return jsonify({
            "status": "success",
            "message": f"Generated and indexed {len(created_events)} events and {len(created_clothes)} clothing items",
            "created_events": created_events,
            "created_clothes": created_clothes,
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
