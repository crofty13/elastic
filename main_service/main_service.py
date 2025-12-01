#!/usr/bin/env python3
"""
RAG (Retrieval-Augmented Generation) workflow for event and clothing recommendations.

This Flask application uses microservices to help users find appropriate
clothing and events based on their queries through a web interface.
Includes OpenTelemetry instrumentation for performance and infrastructure metrics.
"""

import sys
import os
import json
import requests

# Check for required modules
try:
    from openai import OpenAI
    from flask import Flask, render_template, request, jsonify
except ImportError as e:
    print("Error: Required packages not found.")
    print(f"Details: {e}")
    print("\nPlease install Flask, openai, and requests:")
    print("  pip install flask openai requests")
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
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor
    OTEL_AVAILABLE = True
except ImportError as e:
    print("Warning: OpenTelemetry packages not found. Metrics will not be sent.")
    print(f"Details: {e}")
    print("\nTo enable OpenTelemetry, install:")
    print("  pip install opentelemetry-api opentelemetry-sdk")
    print("  pip install opentelemetry-exporter-otlp-proto-http")
    print("  pip install opentelemetry-instrumentation-flask")
    print("  pip install opentelemetry-instrumentation-requests")
    print("  pip install opentelemetry-instrumentation-openai")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set.")
    print("Please set OPENAI_API_KEY environment variable")
    sys.exit(1)

# Microservice endpoints (using Kubernetes service names)
EMBED_SERVICE_URL = os.environ.get("EMBED_SERVICE_URL", "http://embed-user-query-service:5002")
QUERY_EVENTS_SERVICE_URL = os.environ.get("QUERY_EVENTS_SERVICE_URL", "http://query-events-service:5004")
QUERY_CLOTHES_SERVICE_URL = os.environ.get("QUERY_CLOTHES_SERVICE_URL", "http://query-clothes-service:5003")

# Static configuration
GENDER = "men"

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
                "service.name=main-service,"
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
        # This ensures trace context is passed in HTTP headers between services
        set_global_textmap(CompositeHTTPPropagator([TraceContextTextMapPropagator()]))
        
        # Instrument Flask, requests, and OpenAI
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()
        OpenAIInstrumentor().instrument()
        
        actual_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", OTEL_ENDPOINT)
        
        print("✓ OpenTelemetry instrumentation enabled")
        print(f"  Endpoint: {actual_endpoint}")
        print(f"  Service: {resource_attrs.get('service.name', 'main-service')}")
        print(f"  API Key configured: {'Yes' if api_key else 'No'}")
        print(f"  Flask instrumentation: Enabled")
        print(f"  Requests instrumentation: Enabled")
        print(f"  OpenAI instrumentation: Enabled")
        
    except Exception as e:
        print(f"Warning: Failed to set up OpenTelemetry: {e}")
        print("  Application will continue without metrics.")


def embed_query(user_query: str) -> list:
    """
    Call the embed_user_query microservice to get embedding vector.
    
    Args:
        user_query: The text query to embed
        
    Returns:
        List[float]: The embedding vector
    """
    try:
        response = requests.post(
            f"{EMBED_SERVICE_URL}/embed",
            json={"query": user_query},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 'success':
            return data.get('embedding')
        else:
            raise ValueError(f"Embedding service error: {data.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to call embed service: {str(e)}")


def query_events(query_vector: list, k: int = 3) -> dict:
    """
    Call the query_events microservice to search for events.
    
    Args:
        query_vector: The embedding vector to search with
        k: Number of results to return
        
    Returns:
        Dict containing events results
    """
    try:
        response = requests.post(
            f"{QUERY_EVENTS_SERVICE_URL}/query",
            json={
                "query_vector": query_vector,
                "k": k
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        print(f"\n[DEBUG] query_events response: {json.dumps(data, indent=2)}")
        if data.get('status') == 'success':
            # Format response to match original structure
            events_list = data.get('results', [])
            return {
                "hits": {
                    "hits": [
                        {"_source": event} for event in events_list
                    ]
                }
            }
        else:
            raise ValueError(f"Query events service error: {data.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to call query events service: {str(e)}")


def get_clothes_list(gender: str, occation: str = None) -> list:
    """
    Call the query_clothes microservice to search for clothes.
    
    Args:
        gender: Gender filter (e.g., "women", "men")
        occation: Optional occasion string from query_events
        
    Returns:
        List of clothing items
    """
    try:
        payload = {
            "gender": gender
        }
        if occation:
            payload["occation"] = occation
        
        response = requests.post(
            f"{QUERY_CLOTHES_SERVICE_URL}/query",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        print(f"\n[DEBUG] get_clothes_list response: {json.dumps(data, indent=2)}")
        if data.get('status') == 'success':
            return data.get('results', [])
        else:
            raise ValueError(f"Query clothes service error: {data.get('error', 'Unknown error')}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to call query clothes service: {str(e)}")


def get_recommendation(user_query: str) -> str:
    """
    Main RAG workflow function that processes a user query and returns a recommendation.
    
    Args:
        user_query: The user's query about what occasion they need to dress for
        
    Returns:
        A string containing the personalized recommendation
        
    Raises:
        Exception: If any step in the RAG workflow fails
    """
    if not user_query.strip():
        raise ValueError("Please provide a valid query.")
    
    # Step 1: Embed the user query (via microservice)
    query_vector = embed_query(user_query)
    
    # Step 2: Query events using kNN search (via microservice)
    events_result = query_events(query_vector, k=3)
    events_hits = events_result["hits"]["hits"]
    
    if not events_hits:
        raise ValueError("Sorry I couldnt find that event. How about you tell me more your plans")
    
    # Step 3: Extract occasion from the top event
    top_event = events_hits[0]["_source"]
    
    # Extract occasion field (this is the field name in the events index)
    occasion = top_event.get("occasion", "")
    
    # Ensure occasion is a string (not a list)
    if isinstance(occasion, list):
        occation = occasion[0] if occasion else ""
    else:
        occation = occasion if occasion else ""
    
    # Step 4: Query clothes based on extracted event details (via microservice)
    clothes_results = get_clothes_list(
        gender=GENDER,
        occation=occation
    )
    
    # Step 5: Prepare context for OpenAI
    # Format events for the prompt
    events_context = "\n\n".join([
        f"Event {i+1}: {hit['_source'].get('name', 'Unknown')}\n"
        f"Description: {hit['_source'].get('description', 'No description')}\n"
        f"Dos: {', '.join(hit['_source'].get('dos', []))}\n"
        f"Don'ts: {', '.join(hit['_source'].get('donts', []))}"
        for i, hit in enumerate(events_hits)
    ])
    
    # Format clothes for the prompt
    clothes_context = "\n\n".join([
        f"Item {i+1}: {item.get('name', 'Unknown Item')}\n"
        f"Category: {item.get('category', 'N/A')}\n"
        f"Description: {item.get('description', 'No description')}\n"
        f"Color: {item.get('color', 'N/A')}"
        for i, item in enumerate(clothes_results)
    ])
    
    # Create the OpenAI prompt
    system_prompt = """You are a fashion advisor helping users dress appropriately for specific occasions. 
Based on the event details and available clothing items provided, give personalized recommendations."""
    
    user_prompt = f"""Please output the answer to the following question is html format.
    Based on the following event information and available clothing items, provide a detailed write-up 
for what to wear. Only recommend clothes from the items listed below.

USER REQUEST:
{user_query}

MATCHING EVENTS:
{events_context}

AVAILABLE CLOTHING ITEMS:
{clothes_context}

Please provide:
1. A summary of the event.
2. Pick clothese items ONLY from the ones above. pick one labelled top, one labelled bottom, one labelled shoes. Wrtie a brief summary of the outfit and then list the items, there decription and price (which should be formatted in britigh pounds
3. Based on the clothing items you picked add the prices together to show the total.
3. Styling tips and why these choices work for this occasion. This should be no more then 100 words.

"""
    
    # Step 6: Send to OpenAI
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    recommendation = response.choices[0].message.content
    
    return recommendation


@app.route('/')
def index():
    """Render the main chatbot page."""
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    API endpoint to handle chat queries.
    
    Expects JSON with 'query' field.
    Returns JSON with 'recommendation' field or 'error' field.
    """
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({'error': 'Missing query parameter'}), 400
        
        user_query = data['query']
        
        if not user_query.strip():
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        # Get recommendation using the RAG workflow
        recommendation = get_recommendation(user_query)
        
        return jsonify({
            'recommendation': recommendation
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        return jsonify({
            'status': 'healthy',
            'service': 'main-service'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("Main RAG Service")
    print("=" * 60)
    print(f"Embed Service: {EMBED_SERVICE_URL}")
    print(f"Query Events Service: {QUERY_EVENTS_SERVICE_URL}")
    print(f"Query Clothes Service: {QUERY_CLOTHES_SERVICE_URL}")
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    print("\nEndpoints:")
    print("  GET  / - Main chatbot page")
    print("  POST /api/chat - Chat endpoint")
    print("  GET  /health - Health check")
    print("\nStarting server on http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)


