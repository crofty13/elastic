#!/usr/bin/env python3
"""
Simple Flask API to upload event documents to Elasticsearch.

This program receives JSON documents via API endpoint and uploads them
to the Elasticsearch "events" index. Includes OpenTelemetry instrumentation
for performance and infrastructure metrics.
"""

import os
import sys
import json

# Check for required modules
try:
    from flask import Flask, request, jsonify
    from elasticsearch import Elasticsearch
except ImportError as e:
    print("Error: Required packages not found.")
    print(f"Details: {e}")
    print("\nPlease install Flask and elasticsearch:")
    print("  pip install flask elasticsearch")
    sys.exit(1)

# OpenTelemetry imports and setup
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    # Note: ElasticsearchInstrumentor is not needed - Elasticsearch has native OTEL support
    OTEL_AVAILABLE = True
except ImportError as e:
    print("Warning: OpenTelemetry packages not found. Metrics will not be sent.")
    print(f"Details: {e}")
    print("\nTo enable OpenTelemetry, install:")
    print("  pip install opentelemetry-api opentelemetry-sdk")
    print("  pip install opentelemetry-exporter-otlp-proto-http")
    print("  pip install opentelemetry-instrumentation-flask")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("ELASTIC_API_KEY"):
    print("Error: ELASTIC_API_KEY environment variable not set.")
    print("Please run: source keys.sh")
    sys.exit(1)
if not os.environ.get("ELASTIC_ENDPOINT"):
    print("Error: ELASTIC_ENDPOINT environment variable not set.")
    print("Please run: source keys.sh")
    sys.exit(1)

# Elasticsearch endpoint; strip newlines and trailing slash so client requests GET /
ELASTIC_ENDPOINT = os.environ["ELASTIC_ENDPOINT"].strip().rstrip("/")
INDEX_NAME = "events"

# OpenTelemetry configuration (from environment variable OTEL_EXPORTER_OTLP_ENDPOINT)

# Initialize Flask app
app = Flask(__name__)


def setup_opentelemetry():
    """Configure OpenTelemetry to send metrics to Elastic."""
    if not OTEL_AVAILABLE:
        return
    
    try:
        # Get API key from environment (strip in case secret has trailing newline)
        api_key = (os.environ.get("ELASTIC_API_KEY") or "").strip()
        if not api_key:
            print("Warning: ELASTIC_API_KEY not set. OpenTelemetry will not send data.")
            return
        
        # OTEL endpoint must be set in environment
        if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            print("Warning: OTEL_EXPORTER_OTLP_ENDPOINT not set. OpenTelemetry will not send data.")
            return
        
        # Construct the header with ApiKey format (not Bearer)
        otlp_headers = f"Authorization=ApiKey {api_key}"
        if not os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"):
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = otlp_headers
        
        # Set resource attributes if not already set
        if not os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
                "service.name=upload-events-to-elastic,"
                "service.version=1,"
                "deployment.environment=production"
            )
        
        # Create resource from environment variables or defaults
        resource_attrs = {}
        if os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            # Parse OTEL_RESOURCE_ATTRIBUTES format: key1=value1,key2=value2
            for attr in os.environ["OTEL_RESOURCE_ATTRIBUTES"].split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    resource_attrs[key.strip()] = value.strip()
        
        resource = Resource.create(resource_attrs)
        
        # Set up tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure OTLP exporter with API key authentication
        # Use ApiKey format (not Bearer) as required by Elastic
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
            headers={
                "Authorization": f"ApiKey {api_key}"
            }
        )
        
        # Add span processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        
        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        
        # Instrument Flask (this will automatically trace all HTTP requests)
        FlaskInstrumentor().instrument_app(app)
        
        # Note: Elasticsearch has native OpenTelemetry support, so we don't need
        # to use ElasticsearchInstrumentor. The warning about it being disabled is expected.
        
        print("✓ OpenTelemetry instrumentation enabled")
        print(f"  Endpoint: {os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']}")
        print(f"  Service: {resource_attrs.get('service.name', 'upload-events-to-elastic')}")
        print(f"  API Key configured: {'Yes' if api_key else 'No'}")
        print(f"  Flask instrumentation: Enabled")
        print(f"  Traces will be exported automatically for all HTTP requests")
        
    except Exception as e:
        print(f"Warning: Failed to set up OpenTelemetry: {e}")
        print("  Application will continue without metrics.")


def get_elasticsearch_client():
    """Initialize and return Elasticsearch client."""
    api_key = (os.environ.get("ELASTIC_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    return es


@app.route('/upload', methods=['POST'])
def upload_event():
    """
    API endpoint to upload an event document to Elasticsearch.
    
    Expects JSON body with event data.
    Optionally accepts 'id' parameter in query string to specify document ID.
    
    Returns:
        JSON response with Elasticsearch operation result
    """
    try:
        # Get the JSON document from request body
        if not request.is_json:
            return jsonify({
                'error': 'Request must be JSON',
                'status': 'error'
            }), 400
        
        event_doc = request.get_json()
        
        if not event_doc:
            return jsonify({
                'error': 'Empty document provided',
                'status': 'error'
            }), 400
        
        # Get optional document ID from query parameter
        doc_id = request.args.get('id', None)
        
        # Initialize Elasticsearch client
        es = get_elasticsearch_client()
        
        # Upload document to Elasticsearch
        if doc_id:
            # Use specified ID
            result = es.index(
                index=INDEX_NAME,
                id=doc_id,
                body=event_doc
            )
        else:
            # Let Elasticsearch auto-generate ID
            result = es.index(
                index=INDEX_NAME,
                body=event_doc
            )
        
        # Return the Elasticsearch response
        return jsonify({
            'status': 'success',
            'elasticsearch_response': {
                'result': result.get('result'),
                '_id': result.get('_id'),
                '_index': result.get('_index'),
                '_version': result.get('_version'),
                '_shards': result.get('_shards'),
                'seq_no': result.get('_seq_no'),
                'primary_term': result.get('_primary_term')
            }
        }), 200
        
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 400
    except Exception as e:
        # Capture any Elasticsearch errors
        error_details = {
            'error_type': type(e).__name__,
            'error_message': str(e)
        }
        
        # Try to get more details if it's an Elasticsearch exception
        if hasattr(e, 'info'):
            error_details['elasticsearch_info'] = e.info
        
        return jsonify({
            'error': f'Elasticsearch error: {str(e)}',
            'error_details': error_details,
            'status': 'error'
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint. Returns 200 so probes pass; body indicates ES connectivity."""
    try:
        es = get_elasticsearch_client()
        info = es.info()
        return jsonify({
            'status': 'healthy',
            'elasticsearch': {
                'cluster_name': info.get('cluster_name'),
                'version': info.get('version', {}).get('number'),
                'connected': True
            }
        }), 200
    except Exception as e:
        # Return 200 so liveness/readiness probes pass; body shows degraded
        return jsonify({
            'status': 'degraded',
            'elasticsearch': {'connected': False},
            'error': str(e)
        }), 200


if __name__ == "__main__":
    print("=" * 60)
    print("Elasticsearch Event Upload API")
    print("=" * 60)
    print(f"Endpoint: {ELASTIC_ENDPOINT}")
    print(f"Index: {INDEX_NAME}")
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    print("\nEndpoints:")
    print("  POST /upload - Upload an event document")
    print("  GET  /health - Health check")
    print("\nStarting server on http://0.0.0.0:5001")
    print("=" * 60)
    
    # Run on port 5001 to avoid conflict with main.py (port 5000)
    app.run(debug=True, host='0.0.0.0', port=5001)

