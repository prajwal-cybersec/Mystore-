"""Checkout service executing atomic inventory deduction, order creation, and outbox insertion in ONE transaction."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
import structlog
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

    Step 1: For each item:
            UPDATE store_stock SET qty = qty - :qty
            WHERE product_id = :p_id AND city = :city AND qty >= :qty;
            If rowcount == 0 -> query current qty and ABORT with clear OutOfStockError.
    Step 2: Insert order & order_items.
    Step 3: Insert outbox events:
            - "orders.placed"
            - "inventory.changed"
    No direct Kafka call inside this transaction.
    """
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_id = uuid.uuid4()
    total_inr = Decimal("0.00")
    order_items_to_insert = []
    inventory_changes = []

    # Process each item inside the current session transaction
    for it in items:
        p_id = it["product_id"]
        req_qty = int(it["quantity"])
        if req_qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be >= 1")

        # 1. Fetch product metadata
        prod_res = await session.execute(
            text("SELECT id, name, price_inr, sku FROM products WHERE id = :p_id"),
            {"p_id": p_id},
        )
        prod = prod_res.mappings().first()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Product not found: {p_id}")

        prod_name = prod["name"]
        unit_price = Decimal(str(prod["price_inr"]))
        item_total = unit_price * req_qty
        total_inr += item_total

        # 2. Strict atomic deduction with rowcount check
        update_res = await session.execute(
            text("""
                UPDATE store_stock
                SET qty = qty - :qty, updated_at = NOW()
                WHERE product_id = :p_id AND city = :city AND qty >= :qty
            """),
            {"qty": req_qty, "p_id": p_id, "city": city},
        )

        if update_res.rowcount == 0:
            # Query actual stock to report exact remaining quantity
            curr_stock_res = await session.execute(
                text("SELECT qty FROM store_stock WHERE product_id = :p_id AND city = :city"),
                {"p_id": p_id, "city": city},
            )
            curr_stock = curr_stock_res.scalar() or 0
            logger.warning(
                "checkout_stock_depleted",
                product=prod_name,
                city=city,
                requested=req_qty,
                available=curr_stock,
            )
            raise OutOfStockError(
                product_name=prod_name,
                city=city,
                requested=req_qty,
                available=curr_stock,
            )

        # Record item details for insert
        order_items_to_insert.append({
            "id": uuid.uuid4(),
            "order_id": order_id,
            "product_id": p_id,
            "quantity": req_qty,
            "unit_price_inr": unit_price,
            "product_name": prod_name,
            "sku": prod["sku"],
        })

        # Fetch new remaining qty for event
        new_qty_res = await session.execute(
            text("SELECT qty FROM store_stock WHERE product_id = :p_id AND city = :city"),
            {"p_id": p_id, "city": city},
        )
        new_qty = new_qty_res.scalar() or 0
        inventory_changes.append({
            "product_id": str(p_id),
            "city": city,
            "deducted_qty": req_qty,
            "remaining_qty": new_qty,
        })

    # 3. Insert Order
    await session.execute(
        text("""
            INSERT INTO orders (id, customer_id, city, status, total_inr, created_at)
            VALUES (:id, :customer_id, :city, 'placed', :total_inr, NOW())
        """),
        {
            "id": order_id,
            "customer_id": customer_id,
            "city": city,
            "total_inr": total_inr,
        },
    )

    # 4. Insert Order Items
    for oi in order_items_to_insert:
        await session.execute(
            text("""
                INSERT INTO order_items (id, order_id, product_id, quantity, unit_price_inr)
                VALUES (:id, :order_id, :product_id, :quantity, :unit_price_inr)
            """),
            {
                "id": oi["id"],
                "order_id": oi["order_id"],
                "product_id": oi["product_id"],
                "quantity": oi["quantity"],
                "unit_price_inr": oi["unit_price_inr"],
            },
        )

    # 5. Insert Outbox Event: orders.placed
    order_event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.placed",
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "city": city,
        "total_inr": float(total_inr),
        "items": [
            {
                "product_id": str(oi["product_id"]),
                "product_name": oi["product_name"],
                "sku": oi["sku"],
                "quantity": oi["quantity"],
                "unit_price_inr": float(oi["unit_price_inr"]),
            }
            for oi in order_items_to_insert
        ],
    }

    import json
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

    # 6. Insert Outbox Event: inventory.changed for each item
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

    logger.info("checkout_transaction_committed", order_id=str(order_id), total_inr=float(total_inr))
    return {
        "order_id": str(order_id),
        "status": "placed",
        "total_inr": float(total_inr),
        "city": city,
        "items_count": len(order_items_to_insert),
        "order_items": [
            {
                "product_id": str(oi["product_id"]),
                "product_name": oi["product_name"],
                "quantity": oi["quantity"],
                "unit_price_inr": float(oi["unit_price_inr"]),
            }
            for oi in order_items_to_insert
        ],
    }
