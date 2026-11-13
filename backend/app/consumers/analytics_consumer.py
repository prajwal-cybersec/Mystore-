"""Analytics consumer: reads search.events (queries, clicks, zero-result queries),
aggregates click counts and search interest, and maintains trending products in memory and cache.
"""

from __future__ import annotations

import asyncio
import json
import structlog
from typing import Any, Dict, List
from collections import Counter

from app.consumers.base_consumer import IdempotentKafkaConsumer

logger = structlog.stdlib.get_logger(__name__)

# Real-time analytics aggregation counters
query_counter: Counter = Counter()
click_counter: Counter = Counter()
zero_result_counter: Counter = Counter()
trending_products: List[Dict[str, Any]] = []


async def handle_search_event(event: Dict[str, Any]):
    """Process search telemetry events (query, click, zero-results)."""
    event_type = event.get("event_type")
    
    if event_type == "search.query":
        query_text = event.get("query", "").strip().lower()
        if query_text:
            query_counter[query_text] += 1
            if event.get("hits_count", 0) == 0:
                zero_result_counter[query_text] += 1
        logger.info("analytics_query_recorded", query=query_text, hits=event.get("hits_count"))

    elif event_type == "search.click":
        product_id = event.get("product_id")
        if product_id:
            click_counter[product_id] += 1
        logger.info("analytics_click_recorded", product_id=product_id)

    elif event_type == "search.trending_update":
        global trending_products
        trending_products = event.get("trending", [])
        logger.info("analytics_trending_updated", count=len(trending_products))


def get_analytics_snapshot() -> Dict[str, Any]:
    """Retrieve current analytics metrics for insights/X-ray dashboard."""
    return {
        "top_queries": [{"query": q, "count": c} for q, c in query_counter.most_common(10)],
        "top_clicked_products": [{"product_id": pid, "clicks": c} for pid, c in click_counter.most_common(10)],
        "zero_result_queries": [{"query": q, "count": c} for q, c in zero_result_counter.most_common(5)],
        "trending_products": trending_products,
    }


async def run_analytics_consumer():
    consumer = IdempotentKafkaConsumer(
        consumer_name="analytics-consumer",
        topic="search.events",
        group_id="mystore-analytics-group",
    )
    await consumer.start(handler=handle_search_event)


if __name__ == "__main__":
    asyncio.run(run_analytics_consumer())

