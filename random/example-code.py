#!/usr/bin/python3
import os
from elasticsearch import Elasticsearch

# Get API key from environment
ELASTIC_API_KEY = os.environ.get("ELASTIC_API_KEY")
if not ELASTIC_API_KEY:
    raise ValueError("ELASTIC_API_KEY environment variable is not set")

client = Elasticsearch(
  "https://my-observability-project-af75f5.es.eu-west-2.aws.elastic.cloud",
  api_key=ELASTIC_API_KEY
)
print(client.info())



documents = [
  { "index": { "_index": "index_name", "_id": "9780553351927"}},
  {"name": "Snow Crash", "author": "Neal Stephenson", "release_date": "1992-06-01", "page_count": 470},
  { "index": { "_index": "index_name", "_id": "9780441017225"}},
  {"name": "Revelation Space", "author": "Alastair Reynolds", "release_date": "2000-03-15", "page_count": 585},
  { "index": { "_index": "index_name", "_id": "9780451524935"}},
  {"name": "1984", "author": "George Orwell", "release_date": "1985-06-01", "page_count": 328},
  { "index": { "_index": "index_name", "_id": "9781451673319"}},
  {"name": "Fahrenheit 451", "author": "Ray Bradbury", "release_date": "1953-10-15", "page_count": 227},
  { "index": { "_index": "index_name", "_id": "9780060850524"}},
  {"name": "Brave New World", "author": "Aldous Huxley", "release_date": "1932-06-01", "page_count": 268},
  { "index": { "_index": "index_name", "_id": "9780385490818"}},
  {"name": "The Handmaid's Tale", "author": "Margaret Atwood", "release_date": "1985-06-01", "page_count": 311},
]

client.bulk(operations=documents)

client.search(index="index_name", q="snow")
