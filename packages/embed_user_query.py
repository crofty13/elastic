#!/usr/bin/python3
"""
OpenAI embedding utilities for converting text queries into vector embeddings.
"""

import os
from openai import OpenAI
from typing import List

# OpenAI embedding model
EMBEDDING_MODEL = "text-embedding-3-small"


def embed_query(query: str) -> List[float]:
    """
    Convert a text query into an embedding vector using OpenAI's API.
    
    Args:
        query: The text query to embed
    
    Returns:
        List[float]: The embedding vector (length 1536)
    
    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set
    
    Example:
        >>> from embed_user_query import embed_query
        >>> query_vector = embed_query("I'm going to Wimbledon on the weekend")
        >>> print(len(query_vector))  # 1536
    """
    # Get API key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Create embedding
    emb = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query
    )
    
    # Return the embedding vector
    query_vector = emb.data[0].embedding
    return query_vector