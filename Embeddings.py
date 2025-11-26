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
# 📍 Elastic Cloud endpoint
# ------------------------------
ELASTIC_ENDPOINT = "https://my-observability-project-af75f5.es.eu-west-2.aws.elastic.cloud"

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
# 📄 Document ID you want to embed
# ------------------------------
EVENT_DOC_ID = "event_wimbledon_2025"
INDEX_NAME = "events"

# ------------------------------
# 🔍 1. Fetch the document
# ------------------------------
doc = es.get(index=INDEX_NAME, id=EVENT_DOC_ID)["_source"]

# ------------------------------
# 🧩 2. Build embedding text
# ------------------------------
text_for_embedding = (
    doc["description"] + "\n\n"
    + "Women's trends: " + " ".join(doc["fashion_trends_women"]["current_trends"]) + "\n"
    + "Men's trends: " + " ".join(doc["fashion_trends_men"]["current_trends"]) + "\n"
    + "Dos: " + " ".join(doc["dos"]) + "\n"
    + "Donts: " + " ".join(doc["donts"])
)

# ------------------------------
# 🧠 3. Generate OpenAI embedding
# ------------------------------
embedding_response = client.embeddings.create(
    model="text-embedding-3-small",
    input=text_for_embedding
)

embedding_vector = embedding_response.data[0].embedding  # 1536 floats

# ------------------------------
# 💾 4. Update ES document
# ------------------------------
es.update(
    index=INDEX_NAME,
    id=EVENT_DOC_ID,
    body={
        "doc": {
            "embedding": embedding_vector,
            "embedding_model": "openai:text-embedding-3-small"
        }
    }
)

print("Embedding added successfully!")
