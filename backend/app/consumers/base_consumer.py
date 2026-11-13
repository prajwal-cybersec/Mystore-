"""Idempotent base consumer with retry loop and Dead-Letter Queue (DLQ) support."""

from __future__ import annotations

import asyncio
import json
import uuid
import structlog
from typing import Any, Callable, Coroutine, Dict, Optional
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text

from app.database import async_session_factory
from app.kafka_utils import kafka_common_config

logger = structlog.stdlib.get_logger(__name__)


class IdempotentKafkaConsumer:
    """Base class for all consumers guaranteeing exact-once effect via processed_events table."""

    def __init__(
        self,
        consumer_name: str,
        topic: str,
        group_id: str,
        max_retries: int = 3,
    ):
        self.consumer_name = consumer_name
        self.topic = topic
        self.group_id = group_id
        self.dlq_topic = f"{topic}.dlq"
        self.max_retries = max_retries
        self._running = False
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None

    async def start(self, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]):
        """Start listening to Kafka topic with automatic idempotency check and DLQ routing."""
        self._running = True
        cfg = kafka_common_config()
        cfg["group_id"] = self.group_id
        cfg["auto_offset_reset"] = "earliest"
        cfg["enable_auto_commit"] = False

        self._consumer = AIOKafkaConsumer(self.topic, **cfg)
        self._producer = AIOKafkaProducer(**kafka_common_config())

        await self._consumer.start()
        await self._producer.start()
        logger.info("consumer_started", name=self.consumer_name, topic=self.topic, group=self.group_id)

        try:
            while self._running:
                try:
                    msg = await self._consumer.getone()
                    await self._process_message_with_idempotency(msg, handler)
                    await self._consumer.commit()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("consumer_loop_error", name=self.consumer_name, error=str(exc))
                    await asyncio.sleep(1.0)
        finally:
            await self.stop()

    async def stop(self):
        """Clean shutdown of consumer and producer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        logger.info("consumer_stopped", name=self.consumer_name)

    async def _process_message_with_idempotency(
        self,
        msg: Any,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ):
        raw_val = msg.value.decode("utf-8")
        try:
            payload = json.loads(raw_val)
        except Exception:
            payload = {"raw": raw_val}

        event_id = payload.get("event_id") or str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{msg.topic}:{msg.partition}:{msg.offset}"))

        # Step 1: Idempotency check in processed_events table
        async with async_session_factory() as session:
            check_res = await session.execute(
                text("""
                    SELECT 1 FROM processed_events
                    WHERE event_id = :eid AND consumer = :cname
                """),
                {"eid": event_id, "cname": self.consumer_name},
            )
            if check_res.scalar() is not None:
                logger.info("event_already_processed_skipping", event_id=event_id, consumer=self.consumer_name)
                return

        # Step 2: Attempt handler with retries
        attempts = 0
        success = False
        last_error = None

        while attempts < self.max_retries and not success:
            attempts += 1
            try:
                await handler(payload)
                success = True
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "consumer_handler_attempt_failed",
                    consumer=self.consumer_name,
                    attempt=attempts,
                    max_retries=self.max_retries,
                    error=str(exc),
                )
                await asyncio.sleep(0.5 * attempts)

        if success:
            # Step 3: Record event in processed_events table atomically
            async with async_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO processed_events (event_id, consumer, processed_at)
                        VALUES (:eid, :cname, NOW())
                        ON CONFLICT (event_id) DO NOTHING
                    """),
                    {"eid": event_id, "cname": self.consumer_name},
                )
                await session.commit()
            logger.info("event_processed_successfully", event_id=event_id, consumer=self.consumer_name)
        else:
            # Step 4: Route to Dead-Letter Queue (DLQ)
            logger.error(
                "event_exhausted_retries_routing_to_dlq",
                event_id=event_id,
                consumer=self.consumer_name,
                dlq=self.dlq_topic,
                error=str(last_error),
            )
            dlq_payload = {
                "original_event": payload,
                "error": str(last_error),
                "consumer": self.consumer_name,
                "topic": self.topic,
            }
            if self._producer:
                await self._producer.send_and_wait(
                    topic=self.dlq_topic,
                    key=msg.key,
                    value=json.dumps(dlq_payload).encode("utf-8"),
                )

