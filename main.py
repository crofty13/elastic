#!/usr/bin/env python3
"""
RAG (Retrieval-Augmented Generation) workflow for event and clothing recommendations.

This application uses Elasticsearch and OpenAI to help users find appropriate
clothing and events based on their queries.
"""

import sys
import os

# Check for required modules
try:
    from packages.embed_user_query import embed_query
    from packages.query_events import query_events, get_top_event
    from packages.query_clothes import query_clothes, get_clothes_list
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
    # Prompt user for input
    print("What occasion do you need to dress for?")
    user_query = input("> ")
    
    # TODO: Continue with RAG workflow
    # 1. Embed the user query
    # 2. Query events
    # 3. Extract event details
    # 4. Query clothes based on event
    # 5. Present results
    
    print(f"\nYou entered: {user_query}")


if __name__ == "__main__":
    main()

