#!/usr/bin/python3
"""
Elasticsearch query utilities for searching clothes with filters.
"""

import os
from elasticsearch import Elasticsearch
from typing import List, Dict, Any, Optional

# Elasticsearch endpoint (from keys.sh)
ELASTIC_ENDPOINT = os.environ.get("ELASTIC_ENDPOINT")
if not ELASTIC_ENDPOINT:
    raise ValueError("ELASTIC_ENDPOINT environment variable is not set")


def query_clothes(
    gender: str,
    occasion_tags: Optional[List[str]] = None,
    index_name: str = "clothes",
    size: int = 10
) -> Dict[str, Any]:
    """
    Query Elasticsearch for clothes matching specific criteria.
    
    Args:
        gender: Gender filter (e.g., "women", "men") - required
        occasion_tags: Optional list of occasion tags to filter by
        index_name: Name of the index to search (default: "clothes")
        size: Number of results to return (default: 10)
    
    Returns:
        Dict containing the full Elasticsearch response with hits
    
    Example:
        >>> from query_clothes import query_clothes
        >>> # Query with gender and occasion
        >>> results = query_clothes(
        ...     gender="women",
        ...     occasion_tags=["wedding", "garden_party"]
        ... )
        >>> # Query with gender only
        >>> results = query_clothes(gender="women")
    """
    # Get API key from environment
    api_key = os.environ.get("ELASTIC_API_KEY")
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    
    # Initialize Elasticsearch client
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    
    # Build the query
    bool_query = {
        "must": [
            { "term": { "gender": gender } }
        ]
    }
    
    # Add occasion filter if provided
    if occasion_tags:
        bool_query["filter"] = [
            { "terms": { "occasion": occasion_tags } }
        ]
    
    clothes_query = {
        "query": {
            "bool": bool_query
        },
        "size": size
    }
    
    # Execute the search
    clothes_res = es.search(index=index_name, body=clothes_query)
    
    return clothes_res


def get_clothes_list(
    gender: str,
    occasion_tags: Optional[List[str]] = None,
    index_name: str = "clothes",
    size: int = 10
) -> List[Dict[str, Any]]:
    """
    Query Elasticsearch for clothes and return just the list of matching items.
    
    Args:
        gender: Gender filter (e.g., "women", "men") - required
        occasion_tags: Optional list of occasion tags to filter by
        index_name: Name of the index to search (default: "clothes")
        size: Number of results to return (default: 10)
    
    Returns:
        List of dicts containing the _source of matching clothes
    
    Example:
        >>> from query_clothes import get_clothes_list
        >>> # Query with gender and occasion
        >>> clothes = get_clothes_list(
        ...     gender="women",
        ...     occasion_tags=["wedding"]
        ... )
        >>> # Query with gender only
        >>> clothes = get_clothes_list(gender="women")
    """
    res = query_clothes(
        gender=gender,
        occasion_tags=occasion_tags,
        index_name=index_name,
        size=size
    )
    
    clothes_hits = [hit["_source"] for hit in res["hits"]["hits"]]
    return clothes_hits