"""Test that every request body sent in hybrid and vector modes contains the same filter clauses as BM25."""

from unittest.mock import MagicMock, patch
import pytest
from app.search_service import search_hybrid, build_filters, _opensearch_search


@pytest.mark.asyncio
async def test_filter_consistency_in_hybrid_and_vector_modes():
    """Assert every request body sent in hybrid and vector modes contains the same filter clauses as the BM25 body."""
    mock_client = MagicMock()
    mock_search = MagicMock(return_value={
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {
            "categories": {"buckets": []},
            "brands": {"buckets": []},
            "price_stats": {"min": 0, "max": 0, "avg": 0},
        }
    })
    mock_client.search = mock_search

    expected_filters = build_filters(
        category="Electronics",
        min_price=100.0,
        max_price=5000.0,
        city="Bengaluru",
        in_stock_only=True,
    )

    # 1. Test vector mode
    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        await search_hybrid(
            q="headphones",
            category="Electronics",
            min_price=100.0,
            max_price=5000.0,
            city="Bengaluru",
            in_stock_only=True,
            search_mode="vector",
        )

        assert mock_search.call_count >= 1
        vector_call_body = mock_search.call_args_list[-1][1]["body"]
        knn_clause = vector_call_body["query"]["knn"]["embedding"]
        assert "filter" in knn_clause, "Vector kNN query missing filter clause"
        assert knn_clause["filter"]["bool"]["filter"] == expected_filters

    mock_search.reset_mock()

    # 2. Test hybrid mode (both BM25 and kNN must have identical filter clauses)
    with patch("app.search_service.get_opensearch_client", return_value=mock_client), \
         patch("app.search_service.get_embedding_async", return_value=[0.1] * 384):
        await search_hybrid(
            q="headphones",
            category="Electronics",
            min_price=100.0,
            max_price=5000.0,
            city="Bengaluru",
            in_stock_only=True,
            search_mode="hybrid",
        )

        assert mock_search.call_count == 2, f"Expected 2 OpenSearch calls in hybrid mode, got {mock_search.call_count}"
        call_bodies = [c[1]["body"] for c in mock_search.call_args_list]

        bm25_call = next(b for b in call_bodies if "multi_match" in str(b) or "match_all" in str(b))
        knn_call = next(b for b in call_bodies if "knn" in b.get("query", {}))

        bm25_filters = bm25_call["query"]["bool"]["filter"]
        knn_filters = knn_call["query"]["knn"]["embedding"]["filter"]["bool"]["filter"]

        assert bm25_filters == expected_filters
        assert knn_filters == expected_filters
        assert bm25_filters == knn_filters
