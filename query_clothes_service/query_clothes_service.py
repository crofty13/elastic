#!/usr/bin/env python3
"""
Query Clothes Microservice

Flask API service for querying Elasticsearch for clothes matching specific criteria.
Includes OpenTelemetry instrumentation for performance and infrastructure metrics.
"""

import os
import sys

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
    print("Warning: OpenTelemetry packages not found. Metrics will not be sent.")
    print(f"Details: {e}")
    print("\nTo enable OpenTelemetry, install:")
    print("  pip install opentelemetry-api opentelemetry-sdk")
    print("  pip install opentelemetry-exporter-otlp-proto-http")
    print("  pip install opentelemetry-instrumentation-flask")
    print("  pip install opentelemetry-instrumentation-requests")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("ELASTIC_API_KEY"):
    print("Error: ELASTIC_API_KEY environment variable not set.")
    print("Please set ELASTIC_API_KEY environment variable")
    sys.exit(1)

# Elasticsearch endpoint
ELASTIC_ENDPOINT = "https://my-observability-project-af75f5.es.eu-west-2.aws.elastic.cloud"

# OpenTelemetry configuration
OTEL_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "https://af75f5831ca74783b80e17b3166aa46d.ingest.eu-west-2.aws.elastic.cloud:443/v1/traces"
)

# Initialize Flask app
app = Flask(__name__)


def setup_opentelemetry():
    """Configure OpenTelemetry to send metrics to Elastic."""
    if not OTEL_AVAILABLE:
        return
    
    try:
        api_key = os.environ.get("ELASTIC_API_KEY")
        if not api_key:
            print("Warning: ELASTIC_API_KEY not set. OpenTelemetry will not send data.")
            return
        
        if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = OTEL_ENDPOINT
        
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
            endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", OTEL_ENDPOINT),
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
        
        actual_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", OTEL_ENDPOINT)
        
        print("✓ OpenTelemetry instrumentation enabled")
        print(f"  Endpoint: {actual_endpoint}")
        print(f"  Service: {resource_attrs.get('service.name', 'query-clothes-service')}")
        print(f"  API Key configured: {'Yes' if api_key else 'No'}")
        print(f"  Flask instrumentation: Enabled")
        print(f"  Requests instrumentation: Enabled (captures Elasticsearch HTTP calls)")
        
    except Exception as e:
        print(f"Warning: Failed to set up OpenTelemetry: {e}")
        print("  Application will continue without metrics.")


def get_elasticsearch_client():
    """Initialize and return Elasticsearch client."""
    api_key = os.environ.get("ELASTIC_API_KEY")
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    return es


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        es = get_elasticsearch_client()
        info = es.info()
        return jsonify({
            'status': 'healthy',
            'service': 'query-clothes-service',
            'elasticsearch': {
                'cluster_name': info.get('cluster_name'),
                'connected': True
            }
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


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
        occasion_tags = data.get('occasion_tags', None)
        index_name = data.get('index_name', 'clothes')
        size = data.get('size', 10)
        
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
        
        # Execute the search
        clothes_res = es.search(index=index_name, body=clothes_query)
        
        # Extract just the _source from hits
        clothes_list = [hit["_source"] for hit in clothes_res["hits"]["hits"]]
        
        return jsonify({
            'status': 'success',
            'results': clothes_list,
            'total': len(clothes_list)
        }), 200
        
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': f'An error occurred: {str(e)}',
            'status': 'error'
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("Query Clothes Service")
    print("=" * 60)
    print(f"Elasticsearch Endpoint: {ELASTIC_ENDPOINT}")
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    print("\nEndpoints:")
    print("  POST /query - Query clothes from Elasticsearch")
    print("  GET  /health - Health check")
    print("\nStarting server on http://0.0.0.0:5003")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5003)

