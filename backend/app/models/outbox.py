"""Transactional outbox model for reliable Kafka publishing."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.models.base import Base, TimestampMixin


class Outbox(TimestampMixin, Base):
    __tablename__ = "outbox"

    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
