#!/usr/bin/env python3
"""
Script to generate and add embeddings for all event documents in Elasticsearch.

This script:
1. Fetches all documents from the events index
2. Generates OpenAI embeddings for each document
3. Updates each document with its embedding vector
"""

import os
from openai import OpenAI
from elasticsearch import Elasticsearch

# ------------------------------
# 🔐 API KEYS (from environment)
# ------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ELASTIC_API_KEY = os.environ.get("ELASTIC_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
if not ELASTIC_API_KEY:
    raise ValueError("ELASTIC_API_KEY environment variable is not set")

# ------------------------------
# 📍 Elastic Cloud endpoint (from keys.sh)
# ------------------------------
ELASTIC_ENDPOINT = os.environ.get("ELASTIC_ENDPOINT")
if not ELASTIC_ENDPOINT:
    raise ValueError("ELASTIC_ENDPOINT environment variable is not set")
INDEX_NAME = "events"

# ------------------------------
# 🧠 OpenAI client
# ------------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# ------------------------------
# 🔌 Elasticsearch client
# ------------------------------
es = Elasticsearch(
    ELASTIC_ENDPOINT,
    api_key=ELASTIC_API_KEY
)

# ------------------------------
# 🧩 Build embedding text from document
# ------------------------------
def build_embedding_text(doc):
    """
    Build text for embedding from document fields.
    
    Args:
        doc: Document source from Elasticsearch
        
    Returns:
        String containing all relevant text for embedding
    """
    parts = []
    
    # Add name and type
    if doc.get("name"):
        parts.append(f"Event: {doc['name']}")
    if doc.get("type"):
        parts.append(f"Type: {doc['type']}")
    if doc.get("location"):
        parts.append(f"Location: {doc['location']}")
    
    # Add description
    if doc.get("description"):
        parts.append(doc["description"])
    
    # Add occasion and season
    if doc.get("occasion"):
        occasion_list = doc["occasion"] if isinstance(doc["occasion"], list) else [doc["occasion"]]
        parts.append(f"Occasions: {', '.join(occasion_list)}")
    
    if doc.get("season"):
        season_list = doc["season"] if isinstance(doc["season"], list) else [doc["season"]]
        parts.append(f"Seasons: {', '.join(season_list)}")
    
    if doc.get("formality"):
        parts.append(f"Formality: {doc['formality']}")
    
    # Add fashion trends for women
    if doc.get("fashion_trends_women") and doc["fashion_trends_women"].get("current_trends"):
        women_trends = doc["fashion_trends_women"]["current_trends"]
        if isinstance(women_trends, list):
            parts.append(f"Women's fashion trends: {', '.join(women_trends)}")
    
    # Add fashion trends for men
    if doc.get("fashion_trends_men") and doc["fashion_trends_men"].get("current_trends"):
        men_trends = doc["fashion_trends_men"]["current_trends"]
        if isinstance(men_trends, list):
            parts.append(f"Men's fashion trends: {', '.join(men_trends)}")
    
    # Legacy support for dos/donts if they exist
    if doc.get("dos"):
        dos_list = doc["dos"] if isinstance(doc["dos"], list) else [doc["dos"]]
        parts.append(f"Dos: {', '.join(dos_list)}")
    
    if doc.get("donts"):
        donts_list = doc["donts"] if isinstance(doc["donts"], list) else [doc["donts"]]
        parts.append(f"Don'ts: {', '.join(donts_list)}")
    
    return "\n\n".join(parts)


# ------------------------------
# 🔍 1. Fetch all documents from events index
# ------------------------------
print("=" * 60)
print("Fetching all documents from events index...")
print("=" * 60)

# Search for all documents
search_result = es.search(
    index=INDEX_NAME,
    body={
        "query": {"match_all": {}},
        "size": 100  # Adjust if you have more than 100 documents
    }
)

hits = search_result["hits"]["hits"]
total_docs = len(hits)

print(f"Found {total_docs} document(s) in the events index\n")

if total_docs == 0:
    print("No documents found. Exiting.")
    exit(0)

# ------------------------------
# 🧠 2. Process each document
# ------------------------------
success_count = 0
skip_count = 0
error_count = 0

for i, hit in enumerate(hits, 1):
    doc_id = hit["_id"]
    doc = hit["_source"]
    doc_name = doc.get("name", doc_id)
    
    print(f"[{i}/{total_docs}] Processing: {doc_name} (ID: {doc_id})")
    
    # Check if embedding already exists (optional - you can remove this check if you want to regenerate)
    if doc.get("embedding"):
        print(f"  ⚠️  Document already has an embedding. Skipping...")
        print(f"     (Remove this check if you want to regenerate embeddings)")
        skip_count += 1
        continue
    
    try:
        # Build embedding text
        text_for_embedding = build_embedding_text(doc)
        
        # Generate OpenAI embedding
        print(f"  🔄 Generating embedding...")
        embedding_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text_for_embedding
        )
        
        embedding_vector = embedding_response.data[0].embedding
        
        # Update ES document
        print(f"  💾 Updating document in Elasticsearch...")
        es.update(
            index=INDEX_NAME,
            id=doc_id,
            body={
                "doc": {
                    "embedding": embedding_vector,
                    "embedding_model": "openai:text-embedding-3-small"
                }
            }
        )
        
        print(f"  ✅ Embedding added successfully!\n")
        success_count += 1
        
    except Exception as e:
        print(f"  ❌ Error processing document: {e}\n")
        error_count += 1
        continue

# ------------------------------
# 📊 Summary
# ------------------------------
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Total documents: {total_docs}")
print(f"✅ Successfully processed: {success_count}")
print(f"⏭️  Skipped (already had embeddings): {skip_count}")
print(f"❌ Errors: {error_count}")
print("=" * 60)

if success_count > 0:
    print("\n🎉 Embedding generation complete!")
else:
    print("\n⚠️  No new embeddings were generated.")
