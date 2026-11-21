"""Order and OrderItem models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Uuid

from app.models.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'"), default="pending"
    )
    total_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    invoices_expected: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    invoices_ready: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Relationships
    items = relationship("OrderItem", back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_inr: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    sub_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sub_orders.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("seller_offers.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    order = relationship("Order", back_populates="items")
