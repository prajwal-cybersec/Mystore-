"""Health-check router — verifies Postgres, Kafka and OpenSearch connectivity."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import structlog
import urllib3
from aiokafka import AIOKafkaProducer
from fastapi import APIRouter
from opensearchpy import OpenSearch
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.kafka_utils import kafka_common_config

urllib3.disable_warnings()

router = APIRouter(tags=["health"])
logger = structlog.stdlib.get_logger(__name__)


async def _check_postgres() -> str:
    """Run SELECT 1 against PostgreSQL."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.error("postgres_health_check_failed", error=str(exc))
        return f"error: {exc}"


async def _check_kafka() -> str:
    """Verify Kafka broker connectivity."""
    try:
        producer = AIOKafkaProducer(**kafka_common_config())
        await producer.start()
        await producer.stop()
        return "ok"
    except Exception as exc:
        logger.error("kafka_health_check_failed", error=str(exc))
        return f"error: {exc}"


def _check_opensearch_sync() -> str:
    """Ping the OpenSearch cluster synchronously."""
    try:
        client = OpenSearch(
            settings.opensearch_url,
            verify_certs=False,
            ssl_show_warn=False,
        )
        client.info()
        return "ok"
    except Exception as exc:
        logger.error("opensearch_health_check_failed", error=str(exc))
        return f"error: {exc}"


async def _check_opensearch() -> str:
    """Ping OpenSearch in a thread pool."""
    return await asyncio.to_thread(_check_opensearch_sync)


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Aggregate health status of all backing services."""
    pg = await _check_postgres()
    kafka = await _check_kafka()
    opensearch = await _check_opensearch()

    services = {"postgres": pg, "kafka": kafka, "opensearch": opensearch}
    all_ok = all(v == "ok" for v in services.values())

    return {
        "status": "healthy" if all_ok else "degraded",
        "services": services,
    }
