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
import logging
import logging.handlers
from datetime import datetime
import requests

# Check for required modules
try:
    from openai import OpenAI
    from flask import Flask, render_template, request, jsonify
except ImportError as e:
    # Use print here since logger might not be set up yet
    print("ERROR|{\"message\": \"Required packages not found\", \"error\": \"" + str(e).replace('"', '\\"') + "\"}")
    print("ERROR|{\"message\": \"Please install Flask, openai, and requests: pip install flask openai requests\"}")
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
    # Logger not available yet, use print
    print("WARN|{\"message\": \"OpenTelemetry packages not found. Metrics will not be sent.\", \"error\": \"" + str(e).replace('"', '\\"') + "\"}")
    OTEL_AVAILABLE = False

# Check for environment variables
if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR|{\"message\": \"OPENAI_API_KEY environment variable not set\"}")
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
    logger = logging.getLogger('main_service')
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
        
        logger.info("OpenTelemetry instrumentation enabled", extra={
            "endpoint": actual_endpoint,
            "service_name": resource_attrs.get('service.name', 'main-service'),
            "api_key_configured": bool(api_key),
            "flask_instrumentation": True,
            "requests_instrumentation": True,
            "openai_instrumentation": True
        })
        
    except Exception as e:
        logger.error(f"Failed to set up OpenTelemetry: {e}", exc_info=True)
        logger.warning("Application will continue without metrics")


def embed_query(user_query: str) -> list:
    """
    Call the embed_user_query microservice to get embedding vector.
    
    Args:
        user_query: The text query to embed
        
    Returns:
        List[float]: The embedding vector
    """
    logger.info("Calling embed service", extra={
        "service_url": EMBED_SERVICE_URL,
        "query_length": len(user_query)
    })
    
    try:
        response = requests.post(
            f"{EMBED_SERVICE_URL}/embed",
            json={"query": user_query},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            embedding = data.get('embedding')
            logger.info("Embed service call successful", extra={
                "embedding_dimensions": len(embedding) if embedding else 0,
                "status_code": response.status_code
            })
            return embedding
        else:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"Embedding service error: {error_msg}", extra={
                "service_response": data
            })
            raise ValueError(f"Embedding service error: {error_msg}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to call embed service: {str(e)}", exc_info=True, extra={
            "service_url": EMBED_SERVICE_URL
        })
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
    logger.info("Calling query events service", extra={
        "service_url": QUERY_EVENTS_SERVICE_URL,
        "query_vector_length": len(query_vector),
        "query_vector": query_vector[:10],
        "k": k
    })
    
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
        
        # Log the full response as a single JSON message
        logger.info("Query events service response received", extra={
            "status_code": response.status_code,
            "response_data": data
        })
        
        if data.get('status') == 'success':
            # Format response to match original structure
            events_list = data.get('results', [])
            result = {
                "hits": {
                    "hits": [
                        {"_source": event} for event in events_list
                    ]
                }
            }
            logger.info("Query events service call successful", extra={
                "events_count": len(events_list)
            })
            return result
        else:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"Query events service error: {error_msg}", extra={
                "service_response": data
            })
            raise ValueError(f"Query events service error: {error_msg}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to call query events service: {str(e)}", exc_info=True, extra={
            "service_url": QUERY_EVENTS_SERVICE_URL
        })
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
    logger.info("Calling query clothes service", extra={
        "service_url": QUERY_CLOTHES_SERVICE_URL,
        "gender": gender,
        "occation": occation
    })
    
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
        
        # Log the full response as a single JSON message
        logger.info("Query clothes service response received", extra={
            "status_code": response.status_code,
            "response_data": data
        })
        
        if data.get('status') == 'success':
            results = data.get('results', [])
            logger.info("Query clothes service call successful", extra={
                "clothes_count": len(results)
            })
            return results
        else:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"Query clothes service error: {error_msg}", extra={
                "service_response": data
            })
            raise ValueError(f"Query clothes service error: {error_msg}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to call query clothes service: {str(e)}", exc_info=True, extra={
            "service_url": QUERY_CLOTHES_SERVICE_URL
        })
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
    logger.info("Starting recommendation workflow", extra={
        "user_query": user_query,
        "query_length": len(user_query)
    })
    
    if not user_query.strip():
        logger.warning("Empty query received")
        raise ValueError("Please provide a valid query.")
    
    # Step 1: Embed the user query (via microservice)
    logger.info("Step 1: Embedding user query")
    query_vector = embed_query(user_query)
    
    # Step 2: Query events using kNN search (via microservice)
    logger.info("Step 2: Querying events")
    events_result = query_events(query_vector, k=3)
    events_hits = events_result["hits"]["hits"]
    
    if not events_hits:
        logger.warning("No events found for query", extra={
            "user_query": user_query
        })
        raise ValueError("Sorry I couldnt find that event. How about you tell me more your plans")
    
    # Step 3: Extract occasion from the top event
    logger.info("Step 3: Extracting occasion from top event")
    top_event = events_hits[0]["_source"]
    
    # Extract occasion field (this is the field name in the events index)
    occasion = top_event.get("occasion", "")
    
    # Ensure occasion is a string (not a list)
    if isinstance(occasion, list):
        occation = occasion[0] if occasion else ""
    else:
        occation = occasion if occasion else ""
    
    logger.info("Occasion extracted", extra={
        "occation": occation,
        "top_event_name": top_event.get("name", "Unknown")
    })
    
    # Step 4: Query clothes based on extracted event details (via microservice)
    logger.info("Step 4: Querying clothes")
    clothes_results = get_clothes_list(
        gender=GENDER,
        occation=occation
    )
    
    # Step 5: Prepare context for OpenAI
    logger.info("Step 5: Preparing context for OpenAI")
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
    
    logger.info("Context prepared", extra={
        "events_count": len(events_hits),
        "clothes_count": len(clothes_results),
        "events_context_length": len(events_context),
        "clothes_context_length": len(clothes_context)
    })
    
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
    logger.info("Step 6: Calling OpenAI API")
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )
        
        recommendation = response.choices[0].message.content
        
        logger.info("OpenAI API call successful", extra={
            "model": "gpt-4o-mini",
            "recommendation_length": len(recommendation),
            "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None
        })
        
        logger.info("Recommendation workflow completed successfully")
        return recommendation
    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}", exc_info=True)
        raise


@app.route('/')
def index():
    """Render the main chatbot page."""
    logger.info("Index page requested")
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    API endpoint to handle chat queries.
    
    Expects JSON with 'query' field.
    Returns JSON with 'recommendation' field or 'error' field.
    """
    try:
        logger.info("Chat API endpoint called")
        data = request.get_json()
        
        if not data or 'query' not in data:
            logger.warning("Missing query parameter in request")
            return jsonify({'error': 'Missing query parameter'}), 400
        
        user_query = data['query']
        
        if not user_query.strip():
            logger.warning("Empty query received in chat endpoint")
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        # Get recommendation using the RAG workflow
        recommendation = get_recommendation(user_query)
        
        logger.info("Chat API request completed successfully")
        return jsonify({
            'recommendation': recommendation
        })
        
    except ValueError as e:
        logger.warning(f"Validation error in chat endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        logger.debug("Health check requested")
        return jsonify({
            'status': 'healthy',
            'service': 'main-service'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


if __name__ == "__main__":
    logger.info("Starting Main RAG Service", extra={
        "embed_service_url": EMBED_SERVICE_URL,
        "query_events_service_url": QUERY_EVENTS_SERVICE_URL,
        "query_clothes_service_url": QUERY_CLOTHES_SERVICE_URL,
        "gender": GENDER
    })
    
    # Set up OpenTelemetry instrumentation
    setup_opentelemetry()
    
    logger.info("Service endpoints available", extra={
        "endpoints": [
            "GET  / - Main chatbot page",
            "POST /api/chat - Chat endpoint",
            "GET  /health - Health check"
        ]
    })
    
    logger.info("Starting Flask server on http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)


