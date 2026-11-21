"""Product model."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=True)
    category: Mapped[str] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_inr: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attrs: Mapped[dict] = mapped_column(JSONB, server_default="{}", default=dict)
    tryon_supported: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    tryon_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tryon_asset: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tryon_config: Mapped[dict] = mapped_column(JSONB, server_default="{}", default=dict)

    # Relationships
    stock_entries = relationship("StoreStock", back_populates="product", lazy="selectin")
