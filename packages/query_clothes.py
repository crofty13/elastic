#!/usr/bin/python3
"""
Elasticsearch query utilities for searching clothes with filters.
"""

import os
from elasticsearch import Elasticsearch
from typing import List, Dict, Any

# Elasticsearch endpoint
ELASTIC_ENDPOINT = "https://my-observability-project-af75f5.es.eu-west-2.aws.elastic.cloud"


def query_clothes(
    gender: str,
    occasion_tags: List[str],
    season_tags: List[str],
    formality: str,
    index_name: str = "clothes",
    size: int = 10
) -> Dict[str, Any]:
    """
    Query Elasticsearch for clothes matching specific criteria.
    
    Args:
        gender: Gender filter (e.g., "women", "men")
        occasion_tags: List of occasion tags to filter by
        season_tags: List of season tags to filter by
        formality: Formality level (e.g., "formal", "casual")
        index_name: Name of the index to search (default: "clothes")
        size: Number of results to return (default: 10)
    
    Returns:
        Dict containing the full Elasticsearch response with hits
    
    Example:
        >>> from query_clothes import query_clothes
        >>> results = query_clothes(
        ...     gender="women",
        ...     occasion_tags=["wedding", "garden_party"],
        ...     season_tags=["summer"],
        ...     formality="formal"
        ... )
        >>> for hit in results["hits"]["hits"]:
        ...     print(hit["_source"]["name"])
    """
    # Get API key from environment
    api_key = os.environ.get("ELASTIC_API_KEY")
    if not api_key:
        raise ValueError("ELASTIC_API_KEY environment variable is not set")
    
    # Initialize Elasticsearch client
    es = Elasticsearch(ELASTIC_ENDPOINT, api_key=api_key)
    
    # Build the query
    clothes_query = {
        "query": {
            "bool": {
                "must": [
                    { "term": { "gender": gender } }
                ],
                "filter": [
                    { "terms": { "occasion": occasion_tags } },
                    { "terms": { "season": season_tags } },
                    { "term":  { "formality": formality } }
                ]
            }
        },
        "size": size
    }
    
    # Execute the search
    clothes_res = es.search(index=index_name, body=clothes_query)
    
    return clothes_res


def get_clothes_list(
    gender: str,
    occasion_tags: List[str],
    season_tags: List[str],
    formality: str,
    index_name: str = "clothes",
    size: int = 10
) -> List[Dict[str, Any]]:
    """
    Query Elasticsearch for clothes and return just the list of matching items.
    
    Args:
        gender: Gender filter (e.g., "women", "men")
        occasion_tags: List of occasion tags to filter by
        season_tags: List of season tags to filter by
        formality: Formality level (e.g., "formal", "casual")
        index_name: Name of the index to search (default: "clothes")
        size: Number of results to return (default: 10)
    
    Returns:
        List of dicts containing the _source of matching clothes
    
    Example:
        >>> from query_clothes import get_clothes_list
        >>> clothes = get_clothes_list(
        ...     gender="women",
        ...     occasion_tags=["wedding"],
        ...     season_tags=["summer"],
        ...     formality="formal"
        ... )
        >>> for item in clothes:
        ...     print(item["name"])
    """
    res = query_clothes(
        gender=gender,
        occasion_tags=occasion_tags,
        season_tags=season_tags,
        formality=formality,
        index_name=index_name,
        size=size
    )
    
    clothes_hits = [hit["_source"] for hit in res["hits"]["hits"]]
    return clothes_hits