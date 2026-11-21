"""Invoice Service: Gap-free per-seller GST invoice generation and shipment dispatch.

Rules:
1. Gap-free sequential numbering per seller using seller_invoice_counters (UPDATE ... RETURNING).
   Format: INV-2024-25-{seller_code}-{last_no:06d} (e.g. INV-2024-25-KA-000001).
2. Intra-state supply (seller.state == delivery_state) -> CGST (rate/2) + SGST (rate/2), IGST = 0.
   Inter-state supply (seller.state != delivery_state) -> IGST (rate), CGST = 0, SGST = 0.
3. Inserts row into `invoices` and `shipments` in one transaction.
4. Atomically increments `orders.invoices_ready`.
5. Emits `invoice.generated` to outbox.
6. Strictly idempotent: if invoice for sub_order_id already exists, return it without duplicating.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = structlog.stdlib.get_logger(__name__)


def calculate_gst_breakdown(
    subtotal: Decimal,
    category: str,
    seller_state: str,
    delivery_state: str,
) -> Dict[str, Decimal]:
    """Calculate GST breakdown based on place of supply rules."""
    cat_key = (category or "").strip().lower()
    rate = Decimal(str(settings.category_gst_rates.get(cat_key, settings.default_gst_rate)))

    # Total = Taxable + Tax -> Taxable = Total / (1 + rate)
    taxable_value = (subtotal / (Decimal("1") + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_tax = subtotal - taxable_value

    is_intra_state = (seller_state or "").strip().lower() == (delivery_state or "").strip().lower()

    if is_intra_state:
        half_tax = (total_tax / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = half_tax
        sgst = total_tax - cgst  # Prevent 1 paisa rounding drift
        igst = Decimal("0.00")
    else:
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        igst = total_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "taxable_value": taxable_value,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_tax": total_tax,
        "rate": rate,
    }


async def generate_suborder_invoice(
    session: AsyncSession,
    sub_order_id: uuid.UUID | str,
) -> Dict[str, Any]:
    """Generate GST invoice and shipment for a sub-order in a single atomic transaction."""
    sub_oid = uuid.UUID(str(sub_order_id))

    # 1. Idempotency Check: if invoice already exists for this sub_order, return it
    inv_check = await session.execute(
        text("""
            SELECT id, invoice_no, total, issued_at 
            FROM invoices 
            WHERE sub_order_id = :soid
        """),
        {"soid": sub_oid},
    )
    existing_inv = inv_check.mappings().first()
    if existing_inv:
        logger.info("invoice_already_exists", sub_order_id=str(sub_oid), invoice_no=existing_inv["invoice_no"])
        return dict(existing_inv)

    # 2. Fetch sub_order details with seller and parent order
    so_res = await session.execute(
        text("""
            SELECT so.id as sub_order_id, so.order_id, so.seller_id, so.city, so.subtotal, so.tax,
                   s.name as seller_name, s.seller_code, s.state as seller_state, s.gstin,
                   o.city as delivery_city
            FROM sub_orders so
            JOIN sellers s ON s.id = so.seller_id
            JOIN orders o ON o.id = so.order_id
            WHERE so.id = :soid
        """),
        {"soid": sub_oid},
    )
    so = so_res.mappings().first()
    if not so:
        raise ValueError(f"Sub-order {sub_oid} not found.")

    order_id = so["order_id"]
    seller_id = so["seller_id"]
    seller_code = so["seller_code"] or "RET"
    seller_state = so["seller_state"] or "Karnataka"
    delivery_city = (so["delivery_city"] or so["city"] or "").lower()
    delivery_state = settings.city_state_map.get(delivery_city, "Karnataka")

    # 3. Determine category from order items for GST rate
    item_res = await session.execute(
        text("""
            SELECT p.category, oi.quantity, oi.unit_price_inr
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.sub_order_id = :soid
        """),
        {"soid": sub_oid},
    )
    items = item_res.mappings().all()
    first_cat = items[0]["category"] if items else "electronics"

    subtotal = Decimal(str(so["subtotal"]))
    gst = calculate_gst_breakdown(
        subtotal=subtotal,
        category=first_cat,
        seller_state=seller_state,
        delivery_state=delivery_state,
    )

    # 4. Gap-free Invoice Number Generation via seller_invoice_counters
    counter_res = await session.execute(
        text("""
            UPDATE seller_invoice_counters
            SET last_no = last_no + 1
            WHERE seller_id = :sid
            RETURNING last_no
        """),
        {"sid": seller_id},
    )
    counter_row = counter_res.first()
    if not counter_row:
        # Fallback counter insertion if not initialized
        await session.execute(
            text("""
                INSERT INTO seller_invoice_counters (seller_id, last_no)
                VALUES (:sid, 1)
                ON CONFLICT (seller_id) DO UPDATE SET last_no = seller_invoice_counters.last_no + 1
            """),
            {"sid": seller_id},
        )
        counter_row = (1,)

    last_no = counter_row[0]
    invoice_no = f"INV-2024-25-{seller_code}-{last_no:06d}"

    # 5. Insert Invoice
    invoice_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO invoices (
                id, sub_order_id, seller_id, invoice_no,
                taxable_value, cgst, sgst, igst, total, issued_at
            )
            VALUES (
                :id, :soid, :sid, :inv_no,
                :taxable, :cgst, :sgst, :igst, :total, NOW()
            )
        """),
        {
            "id": invoice_id,
            "soid": sub_oid,
            "sid": seller_id,
            "inv_no": invoice_no,
            "taxable": gst["taxable_value"],
            "cgst": gst["cgst"],
            "sgst": gst["sgst"],
            "igst": gst["igst"],
            "total": subtotal,
        },
    )

    # 6. Insert Shipment record
    shipment_id = uuid.uuid4()
    tracking_no = f"TRK-{seller_code}-{uuid.uuid4().hex[:8].upper()}"
    await session.execute(
        text("""
            INSERT INTO shipments (id, sub_order_id, tracking_number, status, created_at)
            VALUES (:id, :soid, :trk, 'label_created', NOW())
        """),
        {"id": shipment_id, "soid": sub_oid, "trk": tracking_no},
    )

    # 7. Atomically increment orders.invoices_ready
    ord_upd = await session.execute(
        text("""
            UPDATE orders
            SET invoices_ready = invoices_ready + 1
            WHERE id = :oid
            RETURNING invoices_ready, invoices_expected
        """),
        {"oid": order_id},
    )
    ord_status = ord_upd.mappings().first()
    invoices_ready = ord_status["invoices_ready"] if ord_status else 1
    invoices_expected = ord_status["invoices_expected"] if ord_status else 1

    # 8. Emit invoice.generated to outbox
    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "invoice.generated",
        "order_id": str(order_id),
        "sub_order_id": str(sub_oid),
        "invoice_id": str(invoice_id),
        "seller_id": str(seller_id),
        "seller_name": so["seller_name"],
        "seller_code": seller_code,
        "invoice_no": invoice_no,
        "taxable_value": float(gst["taxable_value"]),
        "cgst": float(gst["cgst"]),
        "sgst": float(gst["sgst"]),
        "igst": float(gst["igst"]),
        "total": float(subtotal),
        "invoices_ready": invoices_ready,
        "invoices_expected": invoices_expected,
        "all_invoices_ready": invoices_ready >= invoices_expected,
    }

    await session.execute(
        text("""
            INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
            VALUES (:id, 'invoice.generated', :key, CAST(:payload AS jsonb), NOW(), NULL)
        """),
        {
            "id": uuid.uuid4(),
            "key": str(order_id),
            "payload": json.dumps(event_payload),
        },
    )

    logger.info(
        "invoice_generated",
        invoice_no=invoice_no,
        order_id=str(order_id),
        sub_order_id=str(sub_oid),
        invoices_ready=invoices_ready,
        invoices_expected=invoices_expected,
    )

    return {
        "id": invoice_id,
        "sub_order_id": sub_oid,
        "invoice_no": invoice_no,
        "total": subtotal,
        "taxable_value": gst["taxable_value"],
        "cgst": gst["cgst"],
        "sgst": gst["sgst"],
        "igst": gst["igst"],
        "invoices_ready": invoices_ready,
        "invoices_expected": invoices_expected,
    }
