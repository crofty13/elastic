#!/usr/bin/env python3
"""
Embed User Query Microservice

Flask API service for converting text queries into vector embeddings using OpenAI.
Includes OpenTelemetry instrumentation for performance and infrastructure metrics.
"""

import os
import sys

# Check for required modules
try:
    from flask import Flask, request, jsonify
    from openai import OpenAI
except ImportError as e:
    print("Error: Required packages not found.")
    print(f"Details: {e}")
    print("\nPlease install Flask and openai:")
    print("  pip install flask openai")
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
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    OTEL_AVAILABLE = True
except ImportError as e:
    print("Warning: OpenTelemetry packages not found. Metrics will not be sent.")
    print(f"Details: {e}")
    print("\nTo enable OpenTelemetry, install:")
    print("  pip install opentelemetry-api opentelemetry-sdk")
    print("  pip install opentelemetry-exporter-otlp-proto-http")
    print("  pip install opentelemetry-instrumentation-flask")
    print("  pip install opentelemetry-instrumentation-openai")
    print("  pip install opentelemetry-instrumentation-requests")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set.")
    print("Please set OPENAI_API_KEY environment variable")
    sys.exit(1)

# OpenAI embedding model
EMBEDDING_MODEL = "text-embedding-3-small"

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
        # Get API key from environment (use ELASTIC_API_KEY for OTEL)
        api_key = os.environ.get("ELASTIC_API_KEY")
        if not api_key:
            print("Warning: ELASTIC_API_KEY not set. OpenTelemetry will not send data.")
            return
        
        # Set OTEL environment variables if not already set
        if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = OTEL_ENDPOINT
        
        # Construct the header with ApiKey format
        otlp_headers = f"Authorization=ApiKey {api_key}"
        if not os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"):
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = otlp_headers
        
        # Set resource attributes if not already set
        if not os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
                "service.name=embed-user-query-service,"
                "service.version=1,"
                "deployment.environment=production"
            )
        
        # Create resource from environment variables
        resource_attrs = {}
        if os.environ.get("OTEL_RESOURCE_ATTRIBUTES"):
            for attr in os.environ["OTEL_RESOURCE_ATTRIBUTES"].split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    resource_attrs[key.strip()] = value.strip()
        
        resource = Resource.create(resource_attrs)
        
        # Set up tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", OTEL_ENDPOINT),
            headers={
                "Authorization": f"ApiKey {api_key}"
            }
        )
        
        # Add span processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        
        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        
        # Set up trace context propagation (W3C Trace Context format)
        # This ensures trace context is received from incoming HTTP requests
        set_global_textmap(CompositeHTTPPropagator([TraceContextTextMapPropagator()]))
        
        # Instrument Flask, OpenAI, and HTTP requests
        FlaskInstrumentor().instrument_app(app)
        OpenAIInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        
        actual_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", OTEL_ENDPOINT)
        
        print("✓ OpenTelemetry instrumentation enabled")
        print(f"  Endpoint: {actual_endpoint}")
        print(f"  Service: {resource_attrs.get('service.name', 'embed-user-query-service')}")
        print(f"  API Key configured: {'Yes' if api_key else 'No'}")
        print(f"  Flask instrumentation: Enabled")
        print(f"  OpenAI instrumentation: Enabled")
        print(f"  Requests instrumentation: Enabled")
        
    except Exception as e:
        print(f"Warning: Failed to set up OpenTelemetry: {e}")
        print("  Application will continue without metrics.")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        return jsonify({
            'status': 'healthy',
            'service': 'embed-user-query-service'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/embed', methods=['POST'])
def embed_query():
    """
    API endpoint to embed a text query.
    
    Expects JSON body with 'query' field.
    Returns JSON with 'embedding' field (vector of floats).
    """
    try:
        if not request.is_json:
            return jsonify({
                'error': 'Request must be JSON',
                'status': 'error'
            }), 400
        
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                'error': 'Missing query parameter',
                'status': 'error'
            }), 400
        
        query = data['query']
        
        if not query or not query.strip():
            return jsonify({
                'error': 'Query cannot be empty',
                'status': 'error'
            }), 400
        
        # Get API key from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return jsonify({
                'error': 'OPENAI_API_KEY not configured',
                'status': 'error'
            }), 500
        
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Create embedding
        emb = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query
        )
        
        # Return the embedding vector
        query_vector = emb.data[0].embedding
        
        return jsonify({
            'status': 'success',
            'embedding': query_vector,
            'model': EMBEDDING_MODEL,
            'dimensions': len(query_vector)
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
    print("Embed User Query Service")
    print("=" * 60)
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    print("\nEndpoints:")
    print("  POST /embed - Embed a text query")
    print("  GET  /health - Health check")
    print("\nStarting server on http://0.0.0.0:5002")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5002)

