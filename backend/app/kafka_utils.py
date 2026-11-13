"""Kafka helpers — SSL context and common config for producers / consumers."""

from __future__ import annotations

import os
from pathlib import Path
import ssl
from typing import Any

from app.config import settings


def _resolve_ca_path() -> str:
    """Resolve CA path relative to repo root if relative."""
    ca_path = settings.kafka_ca
    if not os.path.isabs(ca_path):
        # backend/app/kafka_utils.py -> backend/app -> backend -> repo root
        root_dir = Path(__file__).resolve().parent.parent.parent
        candidate = root_dir / ca_path
        if candidate.exists():
            return str(candidate)
    return ca_path


def create_kafka_ssl_context() -> ssl.SSLContext:
    """Build an SSL context using the Aiven CA certificate."""
    return ssl.create_default_context(cafile=_resolve_ca_path())


def kafka_common_config() -> dict[str, Any]:
    """Return the connection kwargs shared by AIOKafkaProducer / Consumer."""
    return {
        "bootstrap_servers": settings.kafka_broker,
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "PLAIN",
        "sasl_plain_username": settings.kafka_user,
        "sasl_plain_password": settings.kafka_password,
        "ssl_context": create_kafka_ssl_context(),
    }
