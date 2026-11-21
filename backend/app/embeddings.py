"""Embeddings service using fastembed (ONNX runtime) with graceful fallback."""

from __future__ import annotations

import asyncio
from functools import lru_cache
import structlog
from typing import List, Optional, Tuple

logger = structlog.stdlib.get_logger(__name__)

_model_instance = None
EMBEDDING_DIM = 384


def get_embedding_model():
    """Lazy load embedding model once."""
    global _model_instance
    if _model_instance is None:
        try:
            from fastembed import TextEmbedding
            _model_instance = TextEmbedding("BAAI/bge-small-en-v1.5")
            logger.info("embedding_model_loaded", model="BAAI/bge-small-en-v1.5", dim=EMBEDDING_DIM)
        except Exception as exc:
            logger.warning("embedding_model_load_failed", error=str(exc))
            _model_instance = False
    return _model_instance if _model_instance is not False else None


def compute_embedding(text: str) -> Optional[List[float]]:
    """Compute dense vector embedding for single text, returning list of floats or None."""
    model = get_embedding_model()
    if model is None:
        return None
    try:
        embeddings = list(model.embed([text]))
        if embeddings and len(embeddings) > 0:
            return embeddings[0].tolist()
    except Exception as exc:
        logger.error("compute_embedding_failed", error=str(exc))
    return None


@lru_cache(maxsize=512)
def get_cached_embedding(text: str) -> Optional[Tuple[float, ...]]:
    """LRU-cached query embedding (size 512) keyed by rewritten query text."""
    emb = compute_embedding(text)
    return tuple(emb) if emb is not None else None


async def get_embedding_async(text: str) -> Optional[List[float]]:
    """Non-blocking async wrapper computing embedding in thread pool with 512-entry LRU cache."""
    if not text:
        return None
    cached = await asyncio.to_thread(get_cached_embedding, text)
    return list(cached) if cached is not None else None


def compute_batch_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """Compute dense embeddings for a batch of strings."""
    model = get_embedding_model()
    if model is None:
        return [None] * len(texts)
    try:
        results = []
        for emb in model.embed(texts):
            results.append(emb.tolist())
        return results
    except Exception as exc:
        logger.error("batch_embedding_failed", error=str(exc))
        return [None] * len(texts)

