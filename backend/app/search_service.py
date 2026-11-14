"""Hybrid search service combining BM25 full-text + kNN vector search + RRF/min-max normalization."""

from __future__ import annotations

import structlog
from typing import Any, Dict, List, Optional

from app.opensearch_client import get_opensearch_client, INDEX_NAME
from app.embeddings import compute_embedding
from app.query_understanding import normalize_hinglish_query

logger = structlog.stdlib.get_logger(__name__)


def build_bm25_query(
    search_term: str,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    in_stock_only: bool = False,
) -> Dict[str, Any]:
    """Construct BM25 multi_match query with fuzziness, field boosting, and filters."""
    must_clauses: List[Dict[str, Any]] = []
    filter_clauses: List[Dict[str, Any]] = []

    if search_term:
        must_clauses.append({
            "multi_match": {
                "query": search_term,
                "fields": [
                    "brand^4",
                    "name^3",
                    "name.edge_ngram^2",
                    "category^2",
                    "description^1",
                ],
                "fuzziness": "AUTO",
                "prefix_length": 2,
            }
        })
    else:
        must_clauses.append({"match_all": {}})

    # Facet / Attribute filters
    if category:
        filter_clauses.append({"term": {"category": category}})

    if min_price is not None or max_price is not None:
        price_range: Dict[str, Any] = {}
        if min_price is not None:
            price_range["gte"] = min_price
        if max_price is not None:
            price_range["lte"] = max_price
        filter_clauses.append({"range": {"price_inr": price_range}})

    # City filter using nested city_stock
    if city:
        nested_query: Dict[str, Any] = {
            "nested": {
                "path": "city_stock",
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"city_stock.city": city}},
                        ]
                    }
                }
            }
        }
        if in_stock_only:
            nested_query["nested"]["query"]["bool"]["must"].append(
                {"term": {"city_stock.in_stock": True}}
            )
        filter_clauses.append(nested_query)
    elif in_stock_only:
        filter_clauses.append({"term": {"in_stock": True}})

    return {
        "bool": {
            "must": must_clauses,
            "filter": filter_clauses,
        }
    }


def search_hybrid(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    in_stock_only: bool = False,
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    search_mode: str = "hybrid",  # "hybrid", "bm25", "vector"
) -> Dict[str, Any]:
    """Execute hybrid search combining BM25 keyword matching and kNN vector distance."""
    client = get_opensearch_client()
    raw_query = (q or "").strip()

    # Step 1: Query Understanding & Hinglish Normalization
    normalized = normalize_hinglish_query(raw_query)
    effective_text = normalized["rewritten"] if normalized["rewritten"] else raw_query
    price_intent = normalized.get("extracted_price")
    if price_intent and max_price is None:
        max_price = float(price_intent)

    from_idx = max(0, (page - 1) * size)
    bm25_body = build_bm25_query(
        search_term=effective_text,
        category=category,
        min_price=min_price,
        max_price=max_price,
        city=city,
        in_stock_only=in_stock_only,
    )

    # Sort logic
    sort_body: List[Dict[str, Any]] = []
    if sort == "price_asc":
        sort_body.append({"price_inr": {"order": "asc"}})
    elif sort == "price_desc":
        sort_body.append({"price_inr": {"order": "desc"}})
    else:
        sort_body.append({"_score": {"order": "desc"}})

    # Aggregations for faceted navigation
    aggs_body = {
        "categories": {"terms": {"field": "category", "size": 10}},
        "brands": {"terms": {"field": "brand", "size": 15}},
        "price_stats": {"stats": {"field": "price_inr"}},
    }

    # Vector search logic
    vector = compute_embedding(effective_text) if effective_text else None
    
    # If mode is bm25 or vector is unavailable, fallback gracefully to BM25
    if search_mode == "bm25" or not vector:
        query_payload = {
            "from": from_idx,
            "size": size,
            "query": bm25_body,
            "sort": sort_body,
            "aggs": aggs_body,
        }
        res = client.search(index=INDEX_NAME, body=query_payload)
        return _format_search_response(res, normalized, page, size)

    # If mode is vector only
    if search_mode == "vector":
        knn_query = {
            "size": size,
            "from": from_idx,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": vector,
                        "k": size,
                    }
                }
            },
            "aggs": aggs_body,
        }
        res = client.search(index=INDEX_NAME, body=knn_query)
        return _format_search_response(res, normalized, page, size)

    # Mode is Hybrid: Reciprocal Rank Fusion (RRF) between BM25 and kNN
    # Query top candidates from both BM25 and Vector
    cand_k = 50
    bm25_res = client.search(index=INDEX_NAME, body={
        "size": cand_k,
        "query": bm25_body,
        "_source": ["id", "sku", "name", "brand", "category", "price_inr", "image_url", "in_stock", "city_stock", "description"],
    })
    
    knn_res = client.search(index=INDEX_NAME, body={
        "size": cand_k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": vector,
                    "k": cand_k,
                }
            }
        },
        "_source": ["id", "sku", "name", "brand", "category", "price_inr", "image_url", "in_stock", "city_stock", "description"],
    })

    # Determine if this was an unmatchable / unknown query where no exact or fuzzy lexical match was found
    bm25_hits_count = len(bm25_res.get("hits", {}).get("hits", []))
    knn_top_score = (
        knn_res.get("hits", {}).get("hits", [])[0].get("_score", 0.0)
        if knn_res.get("hits", {}).get("hits")
        else 0.0
    )

    # If raw_query was provided and BM25 found 0 matches and top vector similarity is below threshold (< 0.795),
    # then this is truly an uncatalogued / non-existent item (e.g. "aeroplane", "spaceship", "asdfghjkl").
    # For valid product searches in Hindi/Devanagari/regional scripts (e.g. "तूर दाल" score ~0.809),
    # the vector matches the exact item (Tata Toor Dal) so it must be returned as valid search results!
    is_not_found = False
    similar_hits = []
    if raw_query and bm25_hits_count == 0 and knn_top_score < 0.795:
        is_not_found = True
        # Take top 4 closest items as "similar products you might like"
        for hit in knn_res.get("hits", {}).get("hits", [])[:4]:
            doc = hit["_source"]
            doc["score"] = hit.get("_score")
            similar_hits.append(doc)

    # Apply RRF (k=60 standard)
    rrf_k = 60
    rrf_scores: Dict[str, float] = {}
    doc_store: Dict[str, Any] = {}

    if not is_not_found:
        for rank, hit in enumerate(bm25_res["hits"]["hits"]):
            doc_id = hit["_id"]
            doc_store[doc_id] = hit["_source"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank + 1))

        for rank, hit in enumerate(knn_res["hits"]["hits"]):
            doc_id = hit["_id"]
            doc_store[doc_id] = hit["_source"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank + 1))

    # Sort docs by final RRF score
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda did: rrf_scores[did], reverse=True)
    
    # Paginate fused results
    paged_ids = sorted_doc_ids[from_idx : from_idx + size]
    hits = []
    for did in paged_ids:
        doc = doc_store[did]
        doc["score"] = rrf_scores[did]
        hits.append(doc)

    total_hits = len(sorted_doc_ids)
    
    # Extract facets from BM25 response
    aggs = bm25_res.get("aggregations", {})

    return {
        "query": {
            "original": raw_query,
            "rewritten": normalized["rewritten"],
            "showing_results_for": normalized["rewritten"] if normalized["rewritten"] != raw_query else None,
            "brand_detected": normalized["brand_preserved"],
            "price_intent": max_price if price_intent else None,
            "not_found": is_not_found,
        },
        "total": 0 if is_not_found else total_hits,
        "page": page,
        "size": size,
        "hits": hits,
        "similar_hits": similar_hits,
        "facets": {
            "categories": aggs.get("categories", {}).get("buckets", []),
            "brands": aggs.get("brands", {}).get("buckets", []),
            "price_stats": aggs.get("price_stats", {}),
        },
    }


def _format_search_response(res: Dict[str, Any], normalized: Dict[str, Any], page: int, size: int) -> Dict[str, Any]:
    """Helper to format standard OpenSearch response."""
    hits_data = res.get("hits", {})
    total_val = hits_data.get("total", {}).get("value", 0) if isinstance(hits_data.get("total"), dict) else hits_data.get("total", 0)
    
    hits = []
    for h in hits_data.get("hits", []):
        src = h.get("_source", {})
        src["score"] = h.get("_score")
        hits.append(src)

    aggs = res.get("aggregations", {})
    raw_query = normalized["original"]
    return {
        "query": {
            "original": raw_query,
            "rewritten": normalized["rewritten"],
            "showing_results_for": normalized["rewritten"] if normalized["rewritten"] != raw_query else None,
            "brand_detected": normalized["brand_preserved"],
        },
        "total": total_val,
        "page": page,
        "size": size,
        "hits": hits,
        "facets": {
            "categories": aggs.get("categories", {}).get("buckets", []),
            "brands": aggs.get("brands", {}).get("buckets", []),
            "price_stats": aggs.get("price_stats", {}),
        },
    }


def suggest_autocomplete(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Autocomplete suggestions using edge_ngram prefix match on name."""
    client = get_opensearch_client()
    cleaned = (query or "").strip().lower()
    if not cleaned:
        return []

    body = {
        "size": limit,
        "query": {
            "bool": {
                "should": [
                    {"match_phrase_prefix": {"name": {"query": cleaned, "boost": 3}}},
                    {"match": {"name.edge_ngram": {"query": cleaned, "boost": 2}}},
                    {"match": {"brand": {"query": cleaned, "boost": 2}}},
                ]
            }
        },
        "_source": ["id", "sku", "name", "brand", "category", "price_inr", "image_url"],
    }

    res = client.search(index=INDEX_NAME, body=body)
    suggestions = []
    for h in res.get("hits", {}).get("hits", []):
        suggestions.append(h["_source"])
    return suggestions

