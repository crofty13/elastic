#!/usr/bin/env python3
"""
RAG (Retrieval-Augmented Generation) workflow for event and clothing recommendations.

This Flask application uses Elasticsearch and OpenAI to help users find appropriate
clothing and events based on their queries through a web interface.
"""

import sys
import os
import json

# Check for required modules
try:
    from packages.embed_user_query import embed_query
    from packages.query_events import query_events, get_top_event
    from packages.query_clothes import query_clothes, get_clothes_list
    from openai import OpenAI
    from flask import Flask, render_template, request, jsonify
except ImportError as e:
    print("Error: Required packages not found.")
    print(f"Details: {e}")
    print("\nPlease run the setup script first:")
    print("  chmod +x setup.sh")
    print("  ./setup.sh")
    print("\nOr manually install:")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Check for environment variables
if not os.environ.get("ELASTIC_API_KEY"):
    print("Error: ELASTIC_API_KEY environment variable not set.")
    print("Please run: source keys.sh")
    sys.exit(1)

if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set.")
    print("Please run: source keys.sh")
    sys.exit(1)

# Initialize Flask app
app = Flask(__name__)


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
    
    # Step 1: Embed the user query
    query_vector = embed_query(user_query)
    
    # Step 2: Query events using kNN search (get 3 similar events)
    events_result = query_events(query_vector, k=3)
    events_hits = events_result["hits"]["hits"]
    
    if not events_hits:
        raise ValueError("No matching events found. Please try a different query.")
    
    # Step 3: Extract tags from the top event
    top_event = events_hits[0]["_source"]
    
    # Extract occasion
    occasion = top_event.get("occasion", [])
    
    # Ensure occasion is a list
    occasion_tags = occasion if isinstance(occasion, list) else [occasion]
    
    # Step 4: Query clothes based on extracted event details
    # Default to women's clothing (you can make this configurable)
    gender = "women"
    
    clothes_results = get_clothes_list(
        gender=gender,
        occasion_tags=occasion_tags,
        size=10
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
    
    user_prompt = f"""Based on the following event information and available clothing items, provide a detailed write-up 
for what to wear. Only recommend clothes from the items listed below.

USER REQUEST: {user_query}

MATCHING EVENTS:
{events_context}

AVAILABLE CLOTHING ITEMS:
{clothes_context}

Please provide:
1. A brief summary of the event and dress code
2. Specific clothing recommendations (ONLY from the items listed above)
3. Styling tips and why these choices work for this occasion
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


if __name__ == "__main__":
    # Run the Flask app
    # In production, use a proper WSGI server like gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
