#!/usr/bin/env python3
"""
RAG (Retrieval-Augmented Generation) workflow for event and clothing recommendations.

This application uses Elasticsearch and OpenAI to help users find appropriate
clothing and events based on their queries.
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


def main():
    """
    Main RAG workflow application.
    """
    print("=" * 60)
    print("Event & Clothing Recommendation Assistant")
    print("=" * 60)
    print()
    
    # Step 1: Get user input
    print("What occasion do you need to dress for?")
    user_query = input("> ")
    print()
    
    if not user_query.strip():
        print("Error: Please provide a valid query.")
        return
    
    try:
        # Step 2: Embed the user query
        print("🔍 Analyzing your request...")
        query_vector = embed_query(user_query)
        print(f"✓ Query embedded (vector length: {len(query_vector)})")
        print()
        
        # Step 3: Query events using kNN search (get 3 similar events)
        print("🎪 Searching for matching events...")
        events_result = query_events(query_vector, k=3)
        events_hits = events_result["hits"]["hits"]
        
        if not events_hits:
            print("No matching events found. Please try a different query.")
            return
        
        print(f"✓ Found {len(events_hits)} matching event(s)")
        for i, hit in enumerate(events_hits, 1):
            print(f"  {i}. {hit['_source'].get('name', 'Unknown Event')}")
        print()
        
        # Step 4: Extract tags from the top event
        top_event = events_hits[0]["_source"]
        print(f"📋 Using top match: {top_event.get('name', 'Unknown Event')}")
        
        # Extract occasion
        occasion = top_event.get("occasion", [])
        
        # Ensure occasion is a list
        occasion_tags = occasion if isinstance(occasion, list) else [occasion]
        
        print(f"  Occasion: {', '.join(occasion_tags) if occasion_tags else 'Not specified'}")
        print()
        
        # Step 5: Query clothes based on extracted event details
        print("👔 Searching for appropriate clothing...")
        
        # Default to women's clothing (you can make this configurable)
        gender = "women"
        
        clothes_results = get_clothes_list(
            gender=gender,
            occasion_tags=occasion_tags,
            size=10
        )
        
        print(f"✓ Found {len(clothes_results)} clothing item(s)")
        print()
        
        # Step 6: Prepare context for OpenAI
        print("🤖 Generating personalized recommendation...")
        
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
        
        # Step 7: Send to OpenAI
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
        
        # Step 8: Display the results
        print()
        print("=" * 60)
        print("RECOMMENDATION")
        print("=" * 60)
        print()
        print(recommendation)
        print()
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

