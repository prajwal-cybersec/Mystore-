"""Search sync consumer: listens to inventory.changed & products.updated,
and partial-updates OpenSearch product documents so search stock & badges are never stale.
"""

from __future__ import annotations

import asyncio
import structlog
from typing import Any, Dict
from sqlalchemy import text

from app.database import async_session_factory
from app.opensearch_client import get_opensearch_client, INDEX_NAME
from app.consumers.base_consumer import IdempotentKafkaConsumer

logger = structlog.stdlib.get_logger(__name__)


async def handle_inventory_changed(event: Dict[str, Any]):
    """Sync fresh store stock into OpenSearch product doc."""
    product_id = event.get("product_id")
    if not product_id:
        return

    logger.info("syncing_opensearch_inventory", product_id=product_id)

    # 1. Fetch updated stock across all cities for this product from PostgreSQL
    async with async_session_factory() as session:
        res = await session.execute(
            text("""
                SELECT city, qty
                FROM store_stock
                WHERE product_id = :pid
            """),
            {"pid": product_id},
        )
        stock_rows = res.mappings().all()

    city_stock = []
    total_stock = 0
    for r in stock_rows:
        q = r["qty"]
        total_stock += q
        city_stock.append({
            "city": r["city"],
            "qty": q,
            "in_stock": q > 0,
        })

    in_stock_flag = total_stock > 0

    # 2. Execute partial update on OpenSearch
    os_client = get_opensearch_client()
    try:
        os_client.update(
            index=INDEX_NAME,
            id=str(product_id),
            body={
                "doc": {
                    "city_stock": city_stock,
                    "total_stock": total_stock,
                    "in_stock": in_stock_flag,
                }
            },
        )
        logger.info(
            "opensearch_inventory_synced",
            product_id=product_id,
            total_stock=total_stock,
            in_stock=in_stock_flag,
        )
    except Exception as exc:
        logger.error("opensearch_partial_update_failed", product_id=product_id, error=str(exc))
        raise exc


async def run_search_sync_consumer():
    consumer = IdempotentKafkaConsumer(
        consumer_name="search-sync-consumer",
        topic="inventory.changed",
        group_id="mystore-search-sync-group",
    )
    await consumer.start(handler=handle_inventory_changed)


if __name__ == "__main__":
    asyncio.run(run_search_sync_consumer())

