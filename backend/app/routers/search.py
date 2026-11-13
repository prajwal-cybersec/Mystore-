"""Search router exposing /search, /suggest, and search quality endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from app.search_service import search_hybrid, suggest_autocomplete

router = APIRouter(tags=["search"])


@router.get("/search")
async def search_endpoint(
    q: Optional[str] = Query(None, description="Search query string"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_price: Optional[float] = Query(None, description="Minimum price in INR"),
    max_price: Optional[float] = Query(None, description="Maximum price in INR"),
    city: Optional[str] = Query(None, description="Filter by city availability"),
    in_stock: bool = Query(False, description="Filter only items currently in stock"),
    sort: Optional[str] = Query(None, description="Sort order: price_asc, price_desc, or relevance"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    mode: str = Query("hybrid", description="Search mode: hybrid, bm25, or vector"),
) -> Dict[str, Any]:
    """Execute hybrid search across products index."""
    return search_hybrid(
        q=q,
        category=category,
        min_price=min_price,
        max_price=max_price,
        city=city,
        in_stock_only=in_stock,
        sort=sort,
        page=page,
        size=size,
        search_mode=mode,
    )


@router.get("/suggest")
async def suggest_endpoint(
    q: str = Query(..., min_length=1, description="Prefix for autocomplete suggestions"),
    limit: int = Query(8, ge=1, le=20, description="Max suggestions to return"),
) -> List[Dict[str, Any]]:
    """Fast autocomplete suggestions for search bar."""
    return suggest_autocomplete(query=q, limit=limit)

