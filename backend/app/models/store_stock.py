"""Store stock (per-city inventory) model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Uuid

from app.models.base import Base


class StoreStock(Base):
    __tablename__ = "store_stock"
    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_store_stock_qty_non_negative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id"), primary_key=True
    )
    city: Mapped[str] = mapped_column(
        String(128), primary_key=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    product = relationship("Product", back_populates="stock_entries", lazy="selectin")
