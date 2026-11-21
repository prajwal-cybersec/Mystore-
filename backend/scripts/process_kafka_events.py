"""End-to-end event consumer runner: pulls events from Kafka, runs notification handler,
search-sync handler, records idempotency keys, and updates real-time analytics.
"""

from __future__ import annotations

import asyncio
from typing import Any
from aiokafka import AIOKafkaConsumer

from app.kafka_utils import kafka_common_config
from app.consumers.base_consumer import IdempotentKafkaConsumer
from app.consumers.notification_consumer import handle_order_placed
from app.consumers.returns_notification_consumer import handle_return_event
from app.consumers.search_sync_consumer import handle_inventory_changed
from app.consumers.analytics_consumer import handle_search_event
from app.consumers.invoice_consumer import handle_suborder_created


async def run_notification_worker():
    consumer = IdempotentKafkaConsumer(
        consumer_name="notification-worker",
        topic="orders.placed",
        group_id="mystore-notifications-worker",
    )
    await consumer.start(handler=handle_order_placed)


async def run_search_sync_worker():
    consumer = IdempotentKafkaConsumer(
        consumer_name="search-sync-worker",
        topic="inventory.changed",
        group_id="mystore-search-sync-worker",
    )
    await consumer.start(handler=handle_inventory_changed)


async def process_all_existing_kafka_messages_once():
    """Batch poll from beginning of each topic, execute consumers, and commit."""
    # 1. Process orders.placed
    c1 = IdempotentKafkaConsumer("notification-worker", "orders.placed", "batch-test-group")
    cfg = kafka_common_config()
    cfg["auto_offset_reset"] = "earliest"
    cfg["enable_auto_commit"] = False
    
    k_consumer = AIOKafkaConsumer("orders.placed", "inventory.changed", "returns.events", "suborder.created", **cfg)
    await k_consumer.start()
    print("Reading unconsumed messages across topics...")
    
    msg_dict = await k_consumer.getmany(timeout_ms=3000, max_records=20)
    total_processed = 0
    c_ret = IdempotentKafkaConsumer("returns-notification-worker", "returns.events", "batch-test-group")
    c_inv = IdempotentKafkaConsumer("invoice-generator", "suborder.created", "batch-test-group")
    for tp, msgs in msg_dict.items():
        print(f"Topic: {tp.topic} -> {len(msgs)} messages found")
        for m in msgs:
            if tp.topic == "orders.placed":
                await c1._process_message_with_idempotency(m, handle_order_placed)
            elif tp.topic == "inventory.changed":
                c2 = IdempotentKafkaConsumer("search-sync-worker", "inventory.changed", "batch-test-group")
                await c2._process_message_with_idempotency(m, handle_inventory_changed)
            elif tp.topic == "returns.events":
                await c_ret._process_message_with_idempotency(m, handle_return_event)
            elif tp.topic == "suborder.created":
                await c_inv._process_message_with_idempotency(m, handle_suborder_created)
            total_processed += 1

    await k_consumer.stop()
    print(f"Batch consumer processed {total_processed} events!")


if __name__ == "__main__":
    asyncio.run(process_all_existing_kafka_messages_once())

