# Elastic Search Project

This project contains Python scripts for working with Elasticsearch and OpenAI embeddings.

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Set Environment Variables

Before running any scripts, you need to source the environment variables from `keys.sh`:

```bash
source keys.sh
```

This will set the following environment variables:
- `OPENAI_API_KEY` - Your OpenAI API key
- `ELASTIC_API_KEY` - Your Elasticsearch API key

**Important:** The `keys.sh` file contains sensitive API keys and is excluded from git via `.gitignore`. Never commit this file.

## Usage

### Basic Elasticsearch Connection

```bash
python3 example-code.py
```

### Generate Embeddings

```bash
python3 Embeddings.py
```

### RAG (Retrieval-Augmented Generation) Example

```bash
python3 example-client-rag.py
```

### Query Events Module

The `query_events.py` module provides reusable functions for querying events using k-nearest neighbors search:

```python
from query_events import query_events, get_top_event

# Query for similar events (automatically uses environment variables)
results = query_events(query_vector=[0.1, 0.2, 0.3, ...])

# Get just the top matching event
top_event = get_top_event(query_vector=[0.1, 0.2, 0.3, ...])
```

## Security Notes

- All API keys are now loaded from environment variables
- The `keys.sh` file is gitignored to prevent accidental commits
- Never hardcode API keys in your Python scripts
- Always source `keys.sh` before running scripts

## Files

- `Embeddings.py` - Generate and store OpenAI embeddings in Elasticsearch
- `example-code.py` - Basic Elasticsearch connection example
- `example-client-rag.py` - RAG implementation using OpenAI and Elasticsearch
- `query_events.py` - Reusable module for kNN event queries
- `keys.sh` - Environment variables for API keys (gitignored)
- `requirements.txt` - Python dependencies

