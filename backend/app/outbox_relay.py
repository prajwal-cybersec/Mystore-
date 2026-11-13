"""Outbox relay worker: polls unpublished outbox rows using FOR UPDATE SKIP LOCKED,
publishes each event to Apache Kafka with key=order_id/product_id, and marks them published.
At-least-once delivery guarantee.
"""

from __future__ import annotations

import asyncio
import json
import structlog
from typing import Any, Dict, List
from aiokafka import AIOKafkaProducer
from sqlalchemy import text

from app.database import async_session_factory
from app.kafka_utils import kafka_common_config

logger = structlog.stdlib.get_logger(__name__)


class OutboxRelayWorker:
    def __init__(self, poll_interval: float = 0.5, batch_size: int = 25):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._running = False
        self._producer: AIOKafkaProducer | None = None

    async def start(self):
        """Initialize Kafka producer and enter outbox polling loop."""
        self._running = True
        logger.info("outbox_relay_starting")
        self._producer = AIOKafkaProducer(**kafka_common_config())
        await self._producer.start()
        logger.info("outbox_relay_kafka_connected")

        while self._running:
            try:
                processed_count = await self.process_batch()
                if processed_count == 0:
                    await asyncio.sleep(self.poll_interval)
            except Exception as exc:
                logger.error("outbox_relay_batch_error", error=str(exc))
                await asyncio.sleep(self.poll_interval * 2)

    async def stop(self):
        """Clean shutdown of relay and producer."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            logger.info("outbox_relay_stopped")

    async def process_batch(self) -> int:
        """Fetch unpublished outbox rows with SKIP LOCKED, publish to Kafka, mark published."""
        async with async_session_factory() as session:
            # Atomic fetch with row-level lock skipping already claimed rows
            fetch_query = text("""
                SELECT id, topic, key, payload
                FROM outbox
                WHERE published_at IS NULL
                ORDER BY created_at ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            """)
            result = await session.execute(fetch_query, {"limit": self.batch_size})
            rows = result.mappings().all()

            if not rows:
                return 0

            published_ids = []
            for row in rows:
                row_id = row["id"]
                topic = row["topic"]
                key = str(row["key"]).encode("utf-8") if row["key"] else None
                
                payload_val = row["payload"]
                if isinstance(payload_val, str):
                    val_bytes = payload_val.encode("utf-8")
                else:
                    val_bytes = json.dumps(payload_val).encode("utf-8")

                # Send message to Kafka broker
                await self._producer.send_and_wait(
                    topic=topic,
                    key=key,
                    value=val_bytes,
                )
                published_ids.append(row_id)
                logger.info("outbox_event_published_to_kafka", topic=topic, key=row["key"], row_id=str(row_id))

            # Mark all sent rows as published
            if published_ids:
                update_query = text("""
                    UPDATE outbox
                    SET published_at = NOW()
                    WHERE id = ANY(:ids)
                """)
                await session.execute(update_query, {"ids": published_ids})
                await session.commit()

            return len(published_ids)


async def main():
    relay = OutboxRelayWorker(poll_interval=0.5, batch_size=20)
    try:
        await relay.start()
    except asyncio.CancelledError:
        await relay.stop()


if __name__ == "__main__":
    asyncio.run(main())

