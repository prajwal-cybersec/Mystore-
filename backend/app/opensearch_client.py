"""OpenSearch client and index definitions for MyStore products."""

from __future__ import annotations

import structlog
from typing import Any, Dict
from opensearchpy import OpenSearch

from app.config import settings

logger = structlog.stdlib.get_logger(__name__)

INDEX_NAME = "products"
EMBEDDING_DIM = 384


def get_opensearch_client() -> OpenSearch:
    """Return configured OpenSearch client instance."""
    kwargs: Dict[str, Any] = {
        "verify_certs": settings.opensearch_verify_certs,
        "timeout": 10,
        "max_retries": 1,
        "retry_on_timeout": False,
    }
    if settings.opensearch_ca:
        kwargs["ca_certs"] = settings.opensearch_ca
    return OpenSearch(settings.opensearch_url, **kwargs)


INDEX_MAPPING: Dict[str, Any] = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100,
            "max_ngram_diff": 15,
        },
        "analysis": {
            "tokenizer": {
                "edge_ngram_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                    "token_chars": ["letter", "digit"],
                }
            },
            "analyzer": {
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "edge_ngram_tokenizer",
                    "filter": ["lowercase"],
                },
                "search_text_analyzer": {
                    "type": "standard",
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "sku": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "search_text_analyzer",
                "fields": {
                    "edge_ngram": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                        "search_analyzer": "standard",
                    },
                    "keyword": {"type": "keyword"},
                },
            },
            "brand": {
                "type": "keyword",
                "fields": {
                    "text": {"type": "text"},
                },
            },
            "category": {"type": "keyword"},
            "description": {
                "type": "text",
                "analyzer": "search_text_analyzer",
            },
            "price_inr": {"type": "double"},
            "image_url": {"type": "keyword", "index": False},
            "attrs": {"type": "object", "enabled": False},
            "in_stock": {"type": "boolean"},
            "total_stock": {"type": "integer"},
            "city_stock": {
                "type": "nested",
                "properties": {
                    "city": {"type": "keyword"},
                    "qty": {"type": "integer"},
                    "in_stock": {"type": "boolean"},
                },
            },
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "faiss",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 16,
                    },
                },
            },
        }
    },
}


def ensure_products_index(recreate: bool = False) -> None:
    """Create or update products index with hybrid kNN and edge-ngram mapping."""
    client = get_opensearch_client()
    exists = client.indices.exists(index=INDEX_NAME)
    if exists and recreate:
        logger.info("deleting_existing_opensearch_index", index=INDEX_NAME)
        client.indices.delete(index=INDEX_NAME)
        exists = False

    if not exists:
        logger.info("creating_opensearch_products_index", index=INDEX_NAME)
        client.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
        logger.info("opensearch_products_index_created")
    else:
        logger.info("opensearch_products_index_already_exists")
