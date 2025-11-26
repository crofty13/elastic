#!/usr/bin/python3
"""
Elasticsearch query utilities for event search using kNN (k-nearest neighbors).
"""

import os
from elasticsearch import Elasticsearch
from typing import List, Dict, Any, Optional

# Elasticsearch endpoint
ELASTIC_ENDPOINT = "https://my-observability-project-af75f5.es.eu-west-2.aws.elastic.cloud"


def query_events(
    query_vector: List[float],
    index_name: str = "events",
    k: int = 3,
    num_candidates: int = 10,
    source_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Query Elasticsearch for events using k-nearest neighbors search.
    
    Args:
        query_vector: The embedding vector to search for similar events
        index_name: Name of the index to search (default: "events")
        k: Number of nearest neighbors to return (default: 3)
        num_candidates: Number of candidate documents to consider (default: 10)
        source_fields: List of fields to return in results. If None, returns default fields.
    
    Returns:
        Dict containing the full Elasticsearch response with hits
    
    Example:
        >>> from query_events import query_events
        >>> results = query_events(query_vector=[0.1, 0.2, 0.3, ...])
        >>> top_event = results["hits"]["hits"][0]["_source"]
    """
    # Get API key from environment
    api_key = os.environ.get("ELASTIC_API_KEY")
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    # Default source fields if not provided
    if source_fields is None:
        source_fields = [
            "event_id",
            "name",
            "occasion",
            "season",
            "formality",
            "description",
            "dos",
            "donts",
            "fashion_trends_women",
            "fashion_trends_men"
        ]
    
    # Initialize Elasticsearch client
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    
    # Build the kNN query body
    knn_body = {
        "_source": source_fields,
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": num_candidates
        }
    }
    
    # Execute the search
    res = es.search(index=index_name, body=knn_body)
    
    return res


def get_top_event(
    query_vector: List[float],
    index_name: str = "events",
    source_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Query Elasticsearch and return only the top matching event.
    
    Args:
        query_vector: The embedding vector to search for similar events
        index_name: Name of the index to search (default: "events")
        source_fields: List of fields to return in results. If None, returns default fields.
    
    Returns:
        Dict containing the _source of the top matching event
    
    Example:
        >>> from query_events import get_top_event
        >>> top_event = get_top_event(query_vector=[0.1, 0.2, 0.3, ...])
        >>> print(top_event["name"])
    """
    res = query_events(
        query_vector=query_vector,
        index_name=index_name,
        k=1,
        num_candidates=10,
        source_fields=source_fields
    )
    
    return res["hits"]["hits"][0]["_source"]