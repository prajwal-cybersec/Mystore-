"""Hybrid search service combining BM25 full-text + kNN vector search with resilient PostgreSQL fallback."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy import text

from app.opensearch_client import get_opensearch_client, INDEX_NAME
from app.embeddings import compute_embedding
from app.query_understanding import normalize_hinglish_query
from app.database import engine

logger = structlog.stdlib.get_logger(__name__)

# Circuit breaker state for OpenSearch
_cb_is_open: bool = False
_cb_last_failure: float = 0.0
_cb_cooldown: float = 60.0  # seconds to wait before probing OpenSearch again


# Category aliases mapping legacy and variant terms to active catalogue categories
CATEGORY_ALIASES = {
    "grocery": "Food & Health",
    "atta": "Food & Health",
    "food": "Food & Health",
    "health": "Food & Health",
    "food & health": "Food & Health",
    "food and health": "Food & Health",
    "personal_care": "Beauty",
    "personal care": "Beauty",
    "beauty": "Beauty",
    "cosmetics": "Beauty",
    "home": "Appliances",
    "cookware": "Appliances",
    "home & cookware": "Appliances",
    "appliances": "Appliances",
    "appliance": "Appliances",
    "mobiles": "Mobiles",
    "mobile": "Mobiles",
    "phones": "Mobiles",
    "phone": "Mobiles",
    "electronics": "Electronics",
    "electronic": "Electronics",
    "fashion": "Fashion",
    "clothing": "Fashion",
}


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


def _opensearch_search(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    in_stock_only: bool = False,
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    search_mode: str = "hybrid",
) -> Dict[str, Any]:
    """Execute hybrid search on OpenSearch cluster."""
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

    # Hybrid Mode: RRF between BM25 and kNN
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

    bm25_hits_count = len(bm25_res.get("hits", {}).get("hits", []))
    knn_top_score = (
        knn_res.get("hits", {}).get("hits", [])[0].get("_score", 0.0)
        if knn_res.get("hits", {}).get("hits")
        else 0.0
    )

    is_not_found = False
    similar_hits = []
    if raw_query and bm25_hits_count == 0 and knn_top_score < 0.795:
        is_not_found = True
        for hit in knn_res.get("hits", {}).get("hits", [])[:4]:
            doc = hit["_source"]
            doc["score"] = hit.get("_score")
            similar_hits.append(doc)

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

    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda did: rrf_scores[did], reverse=True)
    paged_ids = sorted_doc_ids[from_idx : from_idx + size]
    hits = []
    for did in paged_ids:
        doc = doc_store[did]
        doc["score"] = rrf_scores[did]
        hits.append(doc)

    total_hits = len(sorted_doc_ids)
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
        "engine": "OpenSearch 3.6.0 Hybrid kNN",
    }


async def _pg_fallback_search(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    in_stock_only: bool = False,
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> Dict[str, Any]:
    """Execute resilient PostgreSQL full-text fallback search."""
    raw_query = (q or "").strip()
    normalized = normalize_hinglish_query(raw_query)
    effective_text = normalized["rewritten"] if normalized["rewritten"] else raw_query
    price_intent = normalized.get("extracted_price")
    if price_intent and max_price is None:
        max_price = float(price_intent)

    # Detect budget intent from words like "cheap", "sasta", "saste"
    low_cost_intent = bool(re.search(r"\b(cheap|sasta|saste|budget|kam daam|low price)\b", (raw_query + " " + effective_text).lower()))
    if low_cost_intent and not sort:
        sort = "price_asc"

    offset = max(0, (page - 1) * size)

    where_clauses = ["1=1"]
    params: Dict[str, Any] = {}

    if category:
        clean_cat = category.strip().lower()
        target_cat = CATEGORY_ALIASES.get(clean_cat, category.strip())
        where_clauses.append("(p.category ILIKE :cat_exact OR p.category ILIKE :cat_pattern OR p.attrs->>'subcategory' ILIKE :cat_pattern)")
        params["cat_exact"] = target_cat
        params["cat_pattern"] = f"%{target_cat}%"

    if min_price is not None:
        where_clauses.append("p.price_inr >= :min_price")
        params["min_price"] = min_price

    if max_price is not None:
        where_clauses.append("p.price_inr <= :max_price")
        params["max_price"] = max_price

    # Stopwords to exclude from strict keyword filters
    stopwords = {"cheap", "sasta", "saste", "sasti", "wala", "wali", "wale", "me", "mein", "ka", "ki", "ke", "best", "quality", "low", "price", "budget"}
    all_query_words = set(raw_query.lower().split() + effective_text.lower().split())
    search_tokens = [w for w in all_query_words if w not in stopwords and len(w) > 1]

    if search_tokens:
        token_clauses = []
        for idx, token in enumerate(search_tokens):
            param_name = f"token_{idx}"
            token_clauses.append(f"""
                (p.name ILIKE :{param_name} 
                 OR p.brand ILIKE :{param_name} 
                 OR p.category ILIKE :{param_name} 
                 OR p.description ILIKE :{param_name})
            """)
            params[param_name] = f"%{token}%"
        where_clauses.append("(" + " OR ".join(token_clauses) + ")")

    if in_stock_only and city:
        where_clauses.append("COALESCE(cur_city.qty, 0) > 0")

    # Order priority
    matched_order = "CASE WHEN city_qty > 0 THEN 0 ELSE 1 END, created_at ASC"
    outer_order = "CASE WHEN city_qty > 0 THEN 0 ELSE 1 END, created_at ASC"
    if sort == "price_asc":
        matched_order = "price_inr ASC"
        outer_order = "price_inr ASC"
    elif sort == "price_desc":
        matched_order = "price_inr DESC"
        outer_order = "price_inr DESC"
    elif search_tokens:
        matched_order = "CASE WHEN name ILIKE :first_token THEN 0 WHEN brand ILIKE :first_token THEN 1 ELSE 2 END, price_inr ASC"
        outer_order = "CASE WHEN name ILIKE :first_token THEN 0 WHEN brand ILIKE :first_token THEN 1 ELSE 2 END, price_inr ASC"
        params["first_token"] = f"%{search_tokens[0]}%"

    where_sql = " AND ".join(where_clauses)

    query_sql = f"""
        WITH matched_products AS (
            SELECT 
                p.id, p.sku, p.name, p.brand, p.category, p.description, 
                p.price_inr, p.image_url, p.attrs, p.created_at,
                COALESCE(cur_city.qty, 0) as city_qty
            FROM products p
            LEFT JOIN store_stock cur_city ON cur_city.product_id = p.id AND cur_city.city = :city_param
            WHERE {where_sql}
        ),
        total_count AS (
            SELECT count(*) as total FROM matched_products
        ),
        paged_products AS (
            SELECT * FROM matched_products
            ORDER BY {matched_order}
            LIMIT :limit OFFSET :offset
        )
        SELECT 
            pp.*,
            (SELECT total FROM total_count) as full_total,
            json_agg(
                json_build_object(
                    'city', ss.city,
                    'qty', ss.qty,
                    'in_stock', (ss.qty > 0)
                )
            ) FILTER (WHERE ss.city IS NOT NULL) as city_stock
        FROM paged_products pp
        LEFT JOIN store_stock ss ON ss.product_id = pp.id
        GROUP BY pp.id, pp.sku, pp.name, pp.brand, pp.category, pp.description, 
                 pp.price_inr, pp.image_url, pp.attrs, pp.created_at, pp.city_qty, full_total
        ORDER BY {outer_order}
    """
    params["city_param"] = city or "Bengaluru"
    params["limit"] = size
    params["offset"] = offset

    async with engine.connect() as conn:
        result = await conn.execute(text(query_sql), params)
        rows = result.fetchall()

    hits = []
    total = 0
    if rows:
        total = rows[0].full_total
        for r in rows:
            attrs = r.attrs
            if isinstance(attrs, str):
                try:
                    attrs = json.loads(attrs)
                except Exception:
                    attrs = {}
            city_stock_list = r.city_stock or []
            total_qty = sum(item.get("qty", 0) for item in city_stock_list)
            
            cur_city_in_stock = False
            for cs in city_stock_list:
                if cs.get("city") == (city or "Bengaluru") and cs.get("qty", 0) > 0:
                    cur_city_in_stock = True
                    break

            hits.append({
                "id": str(r.id),
                "sku": r.sku,
                "name": r.name,
                "brand": r.brand,
                "category": r.category,
                "description": r.description,
                "price_inr": float(r.price_inr),
                "image_url": r.image_url,
                "attrs": attrs or {},
                "in_stock": cur_city_in_stock if city else (total_qty > 0),
                "total_stock": total_qty,
                "city_stock": city_stock_list,
                "score": 1.0,
            })

    # Facets query
    async with engine.connect() as conn:
        cat_res = await conn.execute(text("""
            SELECT category as key, count(*) as doc_count 
            FROM products 
            GROUP BY category 
            ORDER BY doc_count DESC
        """))
        categories = [{"key": r.key, "doc_count": r.doc_count} for r in cat_res.fetchall()]

        brand_res = await conn.execute(text("""
            SELECT brand as key, count(*) as doc_count 
            FROM products 
            GROUP BY brand 
            ORDER BY doc_count DESC 
            LIMIT 15
        """))
        brands = [{"key": r.key, "doc_count": r.doc_count} for r in brand_res.fetchall()]

        price_res = await conn.execute(text("""
            SELECT min(price_inr) as min_p, max(price_inr) as max_p, avg(price_inr) as avg_p 
            FROM products
        """))
        p_row = price_res.fetchone()
        price_stats = {
            "min": float(p_row.min_p) if p_row and p_row.min_p else 0,
            "max": float(p_row.max_p) if p_row and p_row.max_p else 0,
            "avg": float(p_row.avg_p) if p_row and p_row.max_p else 0,
        }

    # If query produced 0 matches, fetch 4 recommendations as similar hits
    similar_hits = []
    is_not_found = (total == 0 and bool(raw_query))
    if is_not_found:
        async with engine.connect() as conn:
            rec_res = await conn.execute(text("""
                SELECT id, sku, name, brand, category, description, price_inr, image_url
                FROM products
                ORDER BY created_at DESC
                LIMIT 4
            """))
            for r in rec_res.fetchall():
                similar_hits.append({
                    "id": str(r.id),
                    "sku": r.sku,
                    "name": r.name,
                    "brand": r.brand,
                    "category": r.category,
                    "description": r.description,
                    "price_inr": float(r.price_inr),
                    "image_url": r.image_url,
                    "in_stock": True,
                    "score": 0.85,
                })

    return {
        "query": {
            "original": raw_query,
            "rewritten": normalized["rewritten"],
            "showing_results_for": normalized["rewritten"] if normalized["rewritten"] != raw_query else None,
            "brand_detected": normalized["brand_preserved"],
            "price_intent": max_price if price_intent else None,
            "not_found": is_not_found,
        },
        "total": total,
        "page": page,
        "size": size,
        "hits": hits,
        "similar_hits": similar_hits,
        "facets": {
            "categories": categories,
            "brands": brands,
            "price_stats": price_stats,
        },
        "engine": "High-Availability Engine (PostgreSQL)",
    }


async def search_hybrid(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    in_stock_only: bool = False,
    sort: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    search_mode: str = "hybrid",
) -> Dict[str, Any]:
    """Execute search: tries OpenSearch first; seamlessly falls back to PostgreSQL on failure."""
    global _cb_is_open, _cb_last_failure

    now = time.time()
    can_try_opensearch = (not _cb_is_open) or (now - _cb_last_failure > _cb_cooldown)

    if can_try_opensearch:
        try:
            res = _opensearch_search(
                q=q,
                category=category,
                min_price=min_price,
                max_price=max_price,
                city=city,
                in_stock_only=in_stock_only,
                sort=sort,
                page=page,
                size=size,
                search_mode=search_mode,
            )
            _cb_is_open = False
            return res
        except Exception as exc:
            _cb_is_open = True
            _cb_last_failure = now
            logger.warning(
                "opensearch_search_failed_activating_postgres_fallback",
                error=str(exc),
                cooldown_sec=_cb_cooldown,
            )

    # OpenSearch is down or circuit is open: route to resilient PostgreSQL fallback
    return await _pg_fallback_search(
        q=q,
        category=category,
        min_price=min_price,
        max_price=max_price,
        city=city,
        in_stock_only=in_stock_only,
        sort=sort,
        page=page,
        size=size,
    )


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
        "engine": "OpenSearch 3.6.0 Hybrid kNN",
    }


async def _pg_fallback_suggest(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Autocomplete suggestions from PostgreSQL using prefix and ILIKE."""
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    async with engine.connect() as conn:
        res = await conn.execute(
            text("""
                SELECT id, sku, name, brand, category, price_inr, image_url
                FROM products
                WHERE name ILIKE :prefix OR brand ILIKE :prefix OR name ILIKE :substr
                ORDER BY CASE WHEN name ILIKE :prefix THEN 0 WHEN brand ILIKE :prefix THEN 1 ELSE 2 END, name ASC
                LIMIT :limit
            """),
            {
                "prefix": f"{cleaned}%",
                "substr": f"%{cleaned}%",
                "limit": limit,
            }
        )
        suggestions = []
        for r in res.fetchall():
            suggestions.append({
                "id": str(r.id),
                "sku": r.sku,
                "name": r.name,
                "brand": r.brand,
                "category": r.category,
                "price_inr": float(r.price_inr),
                "image_url": r.image_url,
            })
        return suggestions


async def suggest_autocomplete(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Autocomplete suggestions: OpenSearch edge_ngram prefix match with PostgreSQL fallback."""
    global _cb_is_open, _cb_last_failure

    cleaned = (query or "").strip().lower()
    if not cleaned:
        return []

    now = time.time()
    can_try_opensearch = (not _cb_is_open) or (now - _cb_last_failure > _cb_cooldown)

    if can_try_opensearch:
        try:
            client = get_opensearch_client()
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
            _cb_is_open = False
            return suggestions
        except Exception as exc:
            _cb_is_open = True
            _cb_last_failure = now
            logger.warning("opensearch_suggest_failed_fallback_to_postgres", error=str(exc))

    return await _pg_fallback_suggest(cleaned, limit=limit)
