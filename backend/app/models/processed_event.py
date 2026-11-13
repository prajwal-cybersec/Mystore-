"""Idempotency tracking for consumed Kafka events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.models.base import Base


class ProcessedEvent(Base):
    """Tracks already-processed event IDs per consumer for idempotency."""

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(
        String(256), primary_key=True
    )
    consumer: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
