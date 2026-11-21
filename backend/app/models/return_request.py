"""ReturnRequest and ReturnStatusHistory models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Uuid

from app.models.base import Base


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_return_requests_quantity_positive"),
        Index("ix_return_requests_order_id", "order_id"),
        Index("ix_return_requests_customer_id", "customer_id"),
        Index("ix_return_requests_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id"), nullable=False
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("order_items.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_urls: Mapped[list[Any]] = mapped_column(
        JSONB, server_default="[]", nullable=False, default=list
    )
    resolution: Mapped[str] = mapped_column(String(16), nullable=False)  # refund | replacement | exchange
    exchange_size: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'requested'"), default="requested"
    )
    item_condition: Mapped[str | None] = mapped_column(String(16), nullable=True)  # resellable | damaged
    refund_amount_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    pickup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Relationships
    history = relationship(
        "ReturnStatusHistory",
        back_populates="return_request",
        order_by="ReturnStatusHistory.created_at.asc()",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ReturnStatusHistory(Base):
    __tablename__ = "return_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    return_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("return_requests.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)  # customer | admin | system
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    return_request = relationship("ReturnRequest", back_populates="history")
