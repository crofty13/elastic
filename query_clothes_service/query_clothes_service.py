#!/usr/bin/env python3
"""
Query Clothes Microservice

Flask API service for querying Elasticsearch for clothes matching specific criteria.
Includes OpenTelemetry instrumentation for performance and infrastructure metrics.
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime

# Check for required modules
try:
    from flask import Flask, request, jsonify
    from elasticsearch import Elasticsearch
except ImportError as e:
    # Use print here since logger might not be set up yet
    print("ERROR|{\"message\": \"Required packages not found\", \"error\": \"" + str(e).replace('"', '\\"') + "\"}")
    print("ERROR|{\"message\": \"Please install Flask and elasticsearch: pip install flask elasticsearch\"}")
    sys.exit(1)

# OpenTelemetry imports and setup
try:
    from opentelemetry import trace
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositeHTTPPropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    OTEL_AVAILABLE = True
except ImportError as e:
    # Logger not available yet, use print
    print("WARN|{\"message\": \"OpenTelemetry packages not found. Metrics will not be sent.\", \"error\": \"" + str(e).replace('"', '\\"') + "\"}")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("ELASTIC_API_KEY"):
    print("ERROR|{\"message\": \"ELASTIC_API_KEY environment variable not set\"}")
    sys.exit(1)
if not os.environ.get("ELASTIC_ENDPOINT"):
    print("ERROR|{\"message\": \"ELASTIC_ENDPOINT environment variable not set\"}")
    sys.exit(1)

# Elasticsearch endpoint (from keys.sh); strip newlines and trailing slash so client requests GET /
ELASTIC_ENDPOINT = os.environ["ELASTIC_ENDPOINT"].strip().rstrip("/")

# OpenTelemetry configuration (from environment variable OTEL_EXPORTER_OTLP_ENDPOINT)

# Initialize Flask app
app = Flask(__name__)

# Configure JSON logging
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter with log level prefix."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields from the record (excluding standard logging fields)
        standard_fields = {'name', 'msg', 'args', 'created', 'filename', 'funcName', 
                          'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message', 
                          'pathname', 'process', 'processName', 'relativeCreated', 'thread', 
                          'threadName', 'exc_info', 'exc_text', 'stack_info'}
        for key, value in record.__dict__.items():
            if key not in standard_fields:
                log_data[key] = value
        
        # Format as JSON with log level prefix
        json_str = json.dumps(log_data, ensure_ascii=False, default=str)
        return f"{record.levelname}|{json_str}"


def setup_logging():
    """Configure logging to stdout and stderr with JSON format."""
    # Create logger
    logger = logging.getLogger('query_clothes_service')
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate logs
    logger.propagate = False
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = JSONFormatter()
    
    # Handler for INFO and below -> stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)
    
    # Handler for WARNING and above -> stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)
    
    # Also configure root logger for third-party libraries
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    
    return logger


# Initialize logger
logger = setup_logging()


def setup_opentelemetry():
    """Configure OpenTelemetry to send metrics to Elastic."""
    if not OTEL_AVAILABLE:
        logger.warning("OpenTelemetry not available - packages not installed")
        return
    
    try:
        api_key = os.environ.get("ELASTIC_API_KEY")
        if not api_key:
            logger.warning("ELASTIC_API_KEY not set. OpenTelemetry will not send data.")
            return
        
        if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not set. OpenTelemetry will not send data.")
            return
        
        otlp_headers = f"Authorization=ApiKey {api_key}"
        if not os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"):
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = otlp_headers
        
        if not os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
                "service.name=query-clothes-service,"
                "service.version=1,"
                "deployment.environment=production"
            )
        
        resource_attrs = {}
        if os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            for attr in os.environ["OTEL_RESOURCE_ATTRIBUTES"].split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    resource_attrs[key.strip()] = value.strip()
        
        resource = Resource.create(resource_attrs)
        tracer_provider = TracerProvider(resource=resource)
        
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
            headers={
                "Authorization": f"ApiKey {api_key}"
            }
        )
        
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(tracer_provider)
        
        # Set up trace context propagation (W3C Trace Context format)
        # This ensures trace context is received from incoming HTTP requests
        set_global_textmap(CompositeHTTPPropagator([TraceContextTextMapPropagator()]))
        
        # Instrument Flask and HTTP requests (for Elasticsearch calls)
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()
        
        logger.info("OpenTelemetry instrumentation enabled", extra={
            "endpoint": os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
            "service_name": resource_attrs.get('service.name', 'query-clothes-service'),
            "api_key_configured": bool(api_key),
            "flask_instrumentation": True,
            "requests_instrumentation": True
        })
        
    except Exception as e:
        logger.error(f"Failed to set up OpenTelemetry: {e}", exc_info=True)
        logger.warning("Application will continue without metrics")


def get_elasticsearch_client():
    """Initialize and return Elasticsearch client."""
    api_key = (os.environ.get("ELASTIC_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    return es


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint. Returns 200 so probes pass; body indicates ES connectivity."""
    try:
        logger.debug("Health check requested")
        es = get_elasticsearch_client()
        info = es.info()
        logger.info("Elasticsearch info API call successful", extra={
            "cluster_name": info.get('cluster_name'),
            "connected": True
        })
        return jsonify({
            'status': 'healthy',
            'service': 'query-clothes-service',
            'elasticsearch': {
                'cluster_name': info.get('cluster_name'),
                'connected': True
            }
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        # Return 200 so liveness/readiness probes pass; body shows degraded
        return jsonify({
            'status': 'degraded',
            'service': 'query-clothes-service',
            'elasticsearch': {'connected': False},
            'error': str(e)
        }), 200


@app.route('/query', methods=['POST'])
def query_clothes():
    """
    API endpoint to query clothes from Elasticsearch.
    
    Expects JSON body with:
    - gender: str (required, e.g., "women", "men")
    - occasion_tags: list[str] (optional)
    - index_name: str (optional, default: "clothes")
    - size: int (optional, default: 10)
    
    Returns JSON with 'results' field containing list of clothes.
    """
    try:
        if not request.is_json:
            return jsonify({
                'error': 'Request must be JSON',
                'status': 'error'
            }), 400
        
        data = request.get_json()
        
        if not data or 'gender' not in data:
            return jsonify({
                'error': 'Missing required parameter: gender',
                'status': 'error'
            }), 400
        
        gender = data['gender']
        occation = data.get('occation', None)  # Note: checking for 'occation' as that's what main_service sends
        occasion_tags = data.get('occasion_tags', None)
        index_name = data.get('index_name', 'clothes')
        size = data.get('size', 10)
        
        # Handle both 'occation' (from main_service) and 'occasion_tags' for compatibility
        if occation and not occasion_tags:
            occasion_tags = [occation] if isinstance(occation, str) else occation
        
        # Initialize Elasticsearch client
        es = get_elasticsearch_client()
        
        # Build the query
        bool_query = {
            "must": [
                { "term": { "gender": gender } }
            ]
        }
        
        # Add occasion filter if provided
        if occasion_tags:
            bool_query["filter"] = [
                { "terms": { "occasion": occasion_tags } }
            ]
        
        clothes_query = {
            "query": {
                "bool": bool_query
            },
            "size": size
        }
        
        # Log before Elasticsearch API call
        logger.info("Calling Elasticsearch search API", extra={
            "endpoint": ELASTIC_ENDPOINT,
            "index": index_name,
            "api_call": "search",
            "query_type": "bool",
            "gender": gender,
            "occasion_tags": occasion_tags,
            "size": size,
            "query_body": clothes_query
        })
        
        # Execute the search
        clothes_res = es.search(index=index_name, body=clothes_query)
        
        logger.info("Elasticsearch search API call successful", extra={
            "index": index_name,
            "hits_count": len(clothes_res.get("hits", {}).get("hits", [])),
            "total_hits": clothes_res.get("hits", {}).get("total", {}).get("value", 0)
        })
        
        # Extract just the _source from hits
        clothes_list = [hit["_source"] for hit in clothes_res["hits"]["hits"]]
        
        logger.info("Query clothes endpoint completed successfully", extra={
            "clothes_returned": len(clothes_list)
        })
        
        return jsonify({
            'status': 'success',
            'results': clothes_list,
            'total': len(clothes_list)
        }), 200
        
    except ValueError as e:
        logger.warning(f"Validation error in query clothes endpoint: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 400
    except Exception as e:
        logger.error(f"Error in query clothes endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'An error occurred: {str(e)}',
            'status': 'error'
        }), 500


if __name__ == "__main__":
    logger.info("Starting Query Clothes Service", extra={
        "elasticsearch_endpoint": ELASTIC_ENDPOINT
    })
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    logger.info("Service endpoints available", extra={
        "endpoints": [
            "POST /query - Query clothes from Elasticsearch",
            "GET  /health - Health check"
        ]
    })
    
    logger.info("Starting Flask server on http://0.0.0.0:5003")
    app.run(debug=True, host='0.0.0.0', port=5003)

