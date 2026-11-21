"""Invoice generation consumer: listens to suborder.created and generates
per-seller GST invoices and shipments idempotently.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
import structlog
from sqlalchemy import text

from app.database import async_session_factory
from app.consumers.base_consumer import IdempotentKafkaConsumer
from app.invoice_service import generate_suborder_invoice

logger = structlog.stdlib.get_logger(__name__)


async def handle_suborder_created(event: Dict[str, Any]):
    """Process a suborder.created event: generate tax invoice and shipment record."""
    sub_order_id = event.get("sub_order_id")
    order_id = event.get("order_id")
    seller_id = event.get("seller_id")

    if not sub_order_id:
        logger.error("missing_sub_order_id_in_event", event=event)
        return

    logger.info("processing_suborder_invoice", sub_order_id=sub_order_id, order_id=order_id, seller_id=seller_id)

    async with async_session_factory() as session:
        async with session.begin():
            await generate_suborder_invoice(session=session, sub_order_id=sub_order_id)


def create_invoice_consumer(group_id: str = "mystore-invoice-workers") -> IdempotentKafkaConsumer:
    """Instantiate IdempotentKafkaConsumer configured for suborder.created topic."""
    return IdempotentKafkaConsumer(
        consumer_name="invoice-generator",
        topic="suborder.created",
        group_id=group_id,
    )


async def run_invoice_worker():
    consumer = create_invoice_consumer()
    await consumer.start(handler=handle_suborder_created)


if __name__ == "__main__":
    asyncio.run(run_invoice_worker())
