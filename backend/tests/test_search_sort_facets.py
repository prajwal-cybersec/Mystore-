"""Tests for hybrid search sorting, facets, and cheap intent consistency."""

from unittest.mock import MagicMock, patch
import pytest
from app.search_service import search_hybrid, _pg_fallback_search


@pytest.mark.asyncio
async def test_hybrid_sort_price_asc_and_desc():
    """Assert hybrid mode correctly sorts merged candidates by price_asc and price_desc."""
    mock_client = MagicMock()
    # Sample hits with distinct prices
    sample_hits = [
        {"_id": "1", "_score": 10.0, "_source": {"id": "1", "name": "Item A", "price_inr": 500.0}},
        {"_id": "2", "_score": 8.0, "_source": {"id": "2", "name": "Item B", "price_inr": 200.0}},
        {"_id": "3", "_score": 5.0, "_source": {"id": "3", "name": "Item C", "price_inr": 800.0}},
    ]

    mock_client.search = MagicMock(return_value={
        "hits": {"hits": sample_hits, "total": {"value": 3}},
        "aggregations": {
            "categories": {"buckets": [{"key": "Electronics", "doc_count": 3}]},
            "brands": {"buckets": [{"key": "boAt", "doc_count": 3}]},
            "price_stats": {"min": 200.0, "max": 800.0, "avg": 500.0},
        }
    })

    # Test price_asc
    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        res_asc = await search_hybrid(q="headphones", sort="price_asc", search_mode="hybrid")
        prices_asc = [h["price_inr"] for h in res_asc["hits"]]
        assert prices_asc == sorted(prices_asc)
        assert prices_asc == [200.0, 500.0, 800.0]
        assert res_asc["total_is_capped"] is True

    # Test price_desc
    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        res_desc = await search_hybrid(q="headphones", sort="price_desc", search_mode="hybrid")
        prices_desc = [h["price_inr"] for h in res_desc["hits"]]
        assert prices_desc == sorted(prices_desc, reverse=True)
        assert prices_desc == [800.0, 500.0, 200.0]


@pytest.mark.asyncio
async def test_hybrid_non_empty_facets():
    """Assert hybrid mode requests and returns non-empty facets from BM25 candidate aggregations."""
    mock_client = MagicMock()
    mock_search = MagicMock(return_value={
        "hits": {"hits": [{"_id": "1", "_score": 1.0, "_source": {"id": "1", "name": "boAt Airdopes", "price_inr": 999.0}}]},
        "aggregations": {
            "categories": {"buckets": [{"key": "Electronics", "doc_count": 10}]},
            "brands": {"buckets": [{"key": "boAt", "doc_count": 8}]},
            "price_stats": {"min": 499.0, "max": 1999.0, "avg": 1199.0},
        }
    })
    mock_client.search = mock_search

    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        res = await search_hybrid(q="airdopes", search_mode="hybrid")

        # Verify aggs were passed in BM25 query in hybrid mode
        bm25_call = next(c[1]["body"] for c in mock_search.call_args_list if "aggs" in c[1]["body"])
        assert "aggs" in bm25_call
        assert "categories" in bm25_call["aggs"]

        # Verify facets in response are non-empty
        assert len(res["facets"]["categories"]) > 0
        assert res["facets"]["categories"][0]["key"] == "Electronics"
        assert len(res["facets"]["brands"]) > 0
        assert res["facets"]["brands"][0]["key"] == "boAt"


@pytest.mark.asyncio
async def test_cheap_intent_sorts_ascending_both_engines():
    """Assert 'sasta phone' (cheap/low-cost intent) automatically sorts ascending on both OpenSearch and Postgres."""
    mock_client = MagicMock()
    sample_hits = [
        {"_id": "1", "_score": 10.0, "_source": {"id": "1", "name": "Costly Phone", "price_inr": 25000.0}},
        {"_id": "2", "_score": 8.0, "_source": {"id": "2", "name": "Budget Phone", "price_inr": 8000.0}},
    ]
    mock_client.search = MagicMock(return_value={
        "hits": {"hits": sample_hits, "total": {"value": 2}},
        "aggregations": {"categories": {"buckets": []}, "brands": {"buckets": []}, "price_stats": {}}
    })

    # 1. OpenSearch path with 'sasta phone'
    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        res_os = await search_hybrid(q="sasta phone", search_mode="hybrid")
        os_prices = [h["price_inr"] for h in res_os["hits"]]
        assert os_prices == [8000.0, 25000.0], f"Expected ascending price order on OpenSearch, got {os_prices}"
        assert "price_intent" in res_os or "price_intent" in res_os.get("query", {})

    # 2. Postgres fallback path with 'sasta phone'
    res_pg = await _pg_fallback_search(q="sasta phone")
    assert res_pg["hits"] is not None
    if len(res_pg["hits"]) > 1:
        pg_prices = [h["price_inr"] for h in res_pg["hits"][:5]]
        assert pg_prices == sorted(pg_prices), f"Expected ascending price order on Postgres fallback, got {pg_prices}"
    assert "price_intent" in res_pg or "price_intent" in res_pg.get("query", {})
