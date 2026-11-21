"""Marketplace seller, offers, sub-orders, invoices, and shipment models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Uuid

from app.models.base import Base


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    seller_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    offers = relationship("SellerOffer", back_populates="seller", cascade="all, delete-orphan")
    sub_orders = relationship("SubOrder", back_populates="seller")


class SellerOffer(Base):
    __tablename__ = "seller_offers"
    __table_args__ = (
        UniqueConstraint("product_id", "seller_id", "city", name="uq_seller_offers_product_seller_city"),
        CheckConstraint("qty >= 0", name="chk_seller_offers_qty_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    price_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

    seller = relationship("Seller", back_populates="offers")


class SellerInvoiceCounter(Base):
    __tablename__ = "seller_invoice_counters"

    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id", ondelete="CASCADE"), primary_key=True
    )
    last_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class SubOrder(Base):
    __tablename__ = "sub_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="placed", server_default=text("'placed'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    seller = relationship("Seller", back_populates="sub_orders")
    invoice = relationship("Invoice", back_populates="sub_order", uselist=False, cascade="all, delete-orphan")
    shipment = relationship("Shipment", back_populates="sub_order", uselist=False, cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("seller_id", "invoice_no", name="uq_invoices_seller_invoice_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    sub_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sub_orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_no: Mapped[str] = mapped_column(String(64), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default=text("0.00"))
    sgst: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default=text("0.00"))
    igst: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default=text("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    sub_order = relationship("SubOrder", back_populates="invoice")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    sub_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sub_orders.id", ondelete="CASCADE"), nullable=False
    )
    tracking_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manifested", server_default=text("'manifested'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    sub_order = relationship("SubOrder", back_populates="shipment")
