"""Checkout service executing multi-seller atomic inventory deduction, sub-orders, and outbox insertion in ONE transaction."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
import structlog
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = structlog.stdlib.get_logger(__name__)


class OutOfStockError(HTTPException):
    def __init__(self, product_name: str, city: str, requested: int, available: int):
        detail = {
            "error": "OUT_OF_STOCK",
            "message": f"Insufficient stock for '{product_name}' in {city}. Requested: {requested}, Available: {available}",
            "product_name": product_name,
            "city": city,
            "requested": requested,
            "available": available,
        }
        super().__init__(status_code=400, detail=detail)


async def execute_checkout_transaction(
    session: AsyncSession,
    customer_id: str,
    city: str,
    items: List[Dict[str, Any]],  # [{"product_id": str, "quantity": int}]
) -> Dict[str, Any]:
    """Execute Checkout in ONE strict atomic PostgreSQL transaction.

    1. For each cart item:
       - Query candidate seller_offers (ordered by city match, lowest price, highest qty).
       - Allocate required quantity across best offers.
       - If total available qty < requested qty -> raise OutOfStockError.
    2. Deadlock Safety: Sort all allocated offer deductions deterministically by offer_id.
    3. Strict atomic guarded deduction:
       UPDATE seller_offers SET qty = qty - :qty WHERE id = :offer_id AND qty >= :qty.
       If rowcount == 0 -> query current qty and abort with OutOfStockError.
       Also update store_stock for backward compatibility with search sync.
    4. Group items into sub_orders by (seller_id, city).
    5. Insert order (grand_total, invoices_expected = len(sub_orders), invoices_ready = 0).
    6. Insert sub_orders and order_items.
    7. Insert outbox events:
       - "orders.placed" (order level)
       - "suborder.created" (one per sub-order)
       - "inventory.changed" (per deducted offer)
    No direct Kafka call inside this transaction.
    """
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_id = uuid.uuid4()
    allocated_offers: List[Dict[str, Any]] = []

    # 1. Select optimal offers for each cart item
    for it in items:
        p_id = it["product_id"]
        req_qty = int(it["quantity"])
        if req_qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be >= 1")

        # Fetch candidate offers for this product across sellers
        offers_res = await session.execute(
            text("""
                SELECT so.id as offer_id, so.product_id, so.seller_id, so.city as offer_city,
                       so.price_inr, so.qty,
                       s.name as seller_name, s.seller_code, s.state as seller_state, s.gstin,
                       p.name as product_name, p.sku, p.category
                FROM seller_offers so
                JOIN sellers s ON s.id = so.seller_id
                JOIN products p ON p.id = so.product_id
                WHERE so.product_id = :p_id AND so.qty > 0
                ORDER BY
                    (CASE WHEN LOWER(so.city) = LOWER(:city) THEN 0 ELSE 1 END) ASC,
                    so.price_inr ASC,
                    so.qty DESC
            """),
            {"p_id": p_id, "city": city},
        )
        candidates = offers_res.mappings().all()

        total_avail = sum(c["qty"] for c in candidates)
        if not candidates or total_avail < req_qty:
            # Query product name for clear error
            p_name_res = await session.execute(
                text("SELECT name FROM products WHERE id = :p_id"),
                {"p_id": p_id},
            )
            p_name = p_name_res.scalar() or "Product"
            logger.warning(
                "checkout_stock_depleted",
                product=p_name,
                city=city,
                requested=req_qty,
                available=total_avail,
            )
            raise OutOfStockError(
                product_name=p_name,
                city=city,
                requested=req_qty,
                available=total_avail,
            )

        # Allocate quantity across top candidate offers
        needed = req_qty
        for c in candidates:
            take = min(needed, c["qty"])
            allocated_offers.append({
                "offer_id": c["offer_id"],
                "product_id": c["product_id"],
                "seller_id": c["seller_id"],
                "seller_name": c["seller_name"],
                "seller_code": c["seller_code"],
                "seller_state": c["seller_state"],
                "seller_gstin": c["gstin"],
                "city": c["offer_city"],
                "unit_price_inr": Decimal(str(c["price_inr"])),
                "quantity": take,
                "product_name": c["product_name"],
                "sku": c["sku"],
                "category": c["category"] or "General",
            })
            needed -= take
            if needed == 0:
                break

    # 2. Deadlock Safety: Sort all offer deductions deterministically by offer_id
    allocated_offers.sort(key=lambda x: str(x["offer_id"]))

    # 3. Strict atomic guarded deduction
    inventory_changes = []
    for alloc in allocated_offers:
        update_res = await session.execute(
            text("""
                UPDATE seller_offers
                SET qty = qty - :qty, updated_at = NOW()
                WHERE id = :offer_id AND qty >= :qty
            """),
            {"qty": alloc["quantity"], "offer_id": alloc["offer_id"]},
        )

        if update_res.rowcount == 0:
            # Check remaining qty to raise accurate OutOfStockError
            curr_res = await session.execute(
                text("SELECT qty FROM seller_offers WHERE id = :offer_id"),
                {"offer_id": alloc["offer_id"]},
            )
            curr_q = curr_res.scalar() or 0
            raise OutOfStockError(
                product_name=alloc["product_name"],
                city=alloc["city"],
                requested=alloc["quantity"],
                available=curr_q,
            )

        # Update store_stock for backward compatibility with search sync
        await session.execute(
            text("""
                UPDATE store_stock
                SET qty = GREATEST(0, qty - :qty), updated_at = NOW()
                WHERE product_id = :p_id AND LOWER(city) = LOWER(:city)
            """),
            {"qty": alloc["quantity"], "p_id": alloc["product_id"], "city": alloc["city"]},
        )

        # Fetch new remaining qty on this offer
        new_q_res = await session.execute(
            text("SELECT qty FROM seller_offers WHERE id = :offer_id"),
            {"offer_id": alloc["offer_id"]},
        )
        new_qty = new_q_res.scalar() or 0
        inventory_changes.append({
            "product_id": str(alloc["product_id"]),
            "city": alloc["city"],
            "deducted_qty": alloc["quantity"],
            "remaining_qty": new_qty,
        })

    # 4. Group allocated items into sub-orders by (seller_id, city)
    sub_orders_map: Dict[tuple, Dict[str, Any]] = {}
    for alloc in allocated_offers:
        key = (str(alloc["seller_id"]), alloc["city"])
        if key not in sub_orders_map:
            sub_orders_map[key] = {
                "id": uuid.uuid4(),
                "seller_id": alloc["seller_id"],
                "seller_name": alloc["seller_name"],
                "seller_code": alloc["seller_code"],
                "seller_state": alloc["seller_state"],
                "seller_gstin": alloc["seller_gstin"],
                "city": alloc["city"],
                "subtotal": Decimal("0.00"),
                "tax": Decimal("0.00"),
                "items": [],
            }

        item_total = alloc["unit_price_inr"] * alloc["quantity"]
        sub_orders_map[key]["subtotal"] += item_total

        # Compute tax per category flat rate (inclusive)
        cat_rate = Decimal(str(settings.category_gst_rates.get(alloc["category"].lower(), settings.default_gst_rate)))
        taxable_val = round(item_total / (Decimal("1.00") + cat_rate), 2)
        item_tax = item_total - taxable_val
        sub_orders_map[key]["tax"] += item_tax

        alloc["sub_order_id"] = sub_orders_map[key]["id"]
        alloc["order_item_id"] = uuid.uuid4()
        sub_orders_map[key]["items"].append(alloc)

    sub_orders_list = list(sub_orders_map.values())
    grand_total = sum(so["subtotal"] for so in sub_orders_list)
    invoices_expected = len(sub_orders_list)

    # 5. Insert Order
    await session.execute(
        text("""
            INSERT INTO orders (
                id, customer_id, city, status, total_inr, grand_total,
                invoices_expected, invoices_ready, created_at
            )
            VALUES (
                :id, :customer_id, :city, 'placed', :total_inr, :grand_total,
                :invoices_expected, 0, NOW()
            )
        """),
        {
            "id": order_id,
            "customer_id": customer_id,
            "city": city,
            "total_inr": grand_total,
            "grand_total": grand_total,
            "invoices_expected": invoices_expected,
        },
    )

    # 6. Insert Sub-Orders
    for so in sub_orders_list:
        await session.execute(
            text("""
                INSERT INTO sub_orders (
                    id, order_id, seller_id, city, subtotal, tax, status, created_at
                )
                VALUES (
                    :id, :order_id, :seller_id, :city, :subtotal, :tax, 'placed', NOW()
                )
            """),
            {
                "id": so["id"],
                "order_id": order_id,
                "seller_id": so["seller_id"],
                "city": so["city"],
                "subtotal": so["subtotal"],
                "tax": so["tax"],
            },
        )

    # 7. Insert Order Items (linked to sub_order_id and offer_id)
    for alloc in allocated_offers:
        await session.execute(
            text("""
                INSERT INTO order_items (
                    id, order_id, product_id, quantity, unit_price_inr, sub_order_id, offer_id
                )
                VALUES (
                    :id, :order_id, :product_id, :quantity, :unit_price_inr, :sub_order_id, :offer_id
                )
            """),
            {
                "id": alloc["order_item_id"],
                "order_id": order_id,
                "product_id": alloc["product_id"],
                "quantity": alloc["quantity"],
                "unit_price_inr": alloc["unit_price_inr"],
                "sub_order_id": alloc["sub_order_id"],
                "offer_id": alloc["offer_id"],
            },
        )

    # 8. Outbox Event: orders.placed
    order_event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.placed",
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "city": city,
        "grand_total": float(grand_total),
        "total_inr": float(grand_total),
        "invoices_expected": invoices_expected,
        "sub_orders": [
            {
                "sub_order_id": str(so["id"]),
                "seller_id": str(so["seller_id"]),
                "seller_code": so["seller_code"],
                "seller_name": so["seller_name"],
                "subtotal": float(so["subtotal"]),
                "tax": float(so["tax"]),
                "items_count": len(so["items"]),
            }
            for so in sub_orders_list
        ],
        "items": [
            {
                "product_id": str(al["product_id"]),
                "product_name": al["product_name"],
                "sku": al["sku"],
                "quantity": al["quantity"],
                "unit_price_inr": float(al["unit_price_inr"]),
                "seller_id": str(al["seller_id"]),
                "seller_code": al["seller_code"],
                "sub_order_id": str(al["sub_order_id"]),
            }
            for al in allocated_offers
        ],
    }

    await session.execute(
        text("""
            INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
            VALUES (:id, 'orders.placed', :key, CAST(:payload AS jsonb), NOW(), NULL)
        """),
        {
            "id": uuid.uuid4(),
            "key": str(order_id),
            "payload": json.dumps(order_event_payload),
        },
    )

    # 9. Outbox Events: suborder.created (ONE per seller sub-order)
    for so in sub_orders_list:
        suborder_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "suborder.created",
            "order_id": str(order_id),
            "sub_order_id": str(so["id"]),
            "seller_id": str(so["seller_id"]),
            "seller_name": so["seller_name"],
            "seller_code": so["seller_code"],
            "seller_state": so["seller_state"],
            "seller_gstin": so["seller_gstin"],
            "delivery_city": city,
            "subtotal": float(so["subtotal"]),
            "tax": float(so["tax"]),
            "items": [
                {
                    "order_item_id": str(it["order_item_id"]),
                    "product_id": str(it["product_id"]),
                    "product_name": it["product_name"],
                    "sku": it["sku"],
                    "category": it["category"],
                    "quantity": it["quantity"],
                    "unit_price_inr": float(it["unit_price_inr"]),
                    "offer_id": str(it["offer_id"]),
                }
                for it in so["items"]
            ],
        }
        await session.execute(
            text("""
                INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
                VALUES (:id, 'suborder.created', :key, CAST(:payload AS jsonb), NOW(), NULL)
            """),
            {
                "id": uuid.uuid4(),
                "key": str(so["id"]),
                "payload": json.dumps(suborder_payload),
            },
        )

    # 10. Outbox Events: inventory.changed for OpenSearch sync
    for inv in inventory_changes:
        inv_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "inventory.changed",
            "order_id": str(order_id),
            "product_id": inv["product_id"],
            "city": inv["city"],
            "deducted_qty": inv["deducted_qty"],
            "remaining_qty": inv["remaining_qty"],
        }
        await session.execute(
            text("""
                INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
                VALUES (:id, 'inventory.changed', :key, CAST(:payload AS jsonb), NOW(), NULL)
            """),
            {
                "id": uuid.uuid4(),
                "key": inv["product_id"],
                "payload": json.dumps(inv_payload),
            },
        )

    logger.info(
        "multiseller_checkout_committed",
        order_id=str(order_id),
        grand_total=float(grand_total),
        sub_orders_count=len(sub_orders_list),
    )

    return {
        "order_id": str(order_id),
        "status": "placed",
        "city": city,
        "total_inr": float(grand_total),
        "grand_total": float(grand_total),
        "invoices_expected": invoices_expected,
        "items_count": len(allocated_offers),
        "sub_orders": [
            {
                "sub_order_id": str(so["id"]),
                "seller": {
                    "id": str(so["seller_id"]),
                    "name": so["seller_name"],
                    "seller_code": so["seller_code"],
                    "state": so["seller_state"],
                },
                "city": so["city"],
                "subtotal": float(so["subtotal"]),
                "tax": float(so["tax"]),
                "items": [
                    {
                        "product_id": str(it["product_id"]),
                        "product_name": it["product_name"],
                        "sku": it["sku"],
                        "quantity": it["quantity"],
                        "unit_price_inr": float(it["unit_price_inr"]),
                    }
                    for it in so["items"]
                ],
            }
            for so in sub_orders_list
        ],
    }
