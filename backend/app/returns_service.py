"""Returns service encapsulating database operations, concurrency locks, and outbox event creation."""

from __future__ import annotations

import json
import secrets
import string
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import structlog
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.returns_policy import (
    ADMIN_ACTION_MAP,
    can_transition,
    check_return_window,
    is_reason_allowed_for_category,
    is_resolution_allowed,
    validate_exchange_size,
    validate_photos,
)

logger = structlog.stdlib.get_logger(__name__)


def generate_return_reference() -> str:
    """Generate reference in format RET- + 6 uppercase alphanumerics."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"RET-{suffix}"


async def create_return_request(
    session: AsyncSession,
    order_id: str,
    customer_id: str,
    order_item_id: str,
    quantity: int,
    reason_code: str,
    resolution: str,
    description: Optional[str] = None,
    photo_urls: Optional[List[str]] = None,
    exchange_size: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate all business rules, lock order_item row, and create return request with outbox event in ONE transaction."""
    photo_urls = photo_urls or []

    # 1. Fetch order
    order_res = await session.execute(
        text("""
            SELECT id, customer_id, city, status, delivered_at
            FROM orders
            WHERE id = :order_id
        """),
        {"order_id": order_id},
    )
    order = order_res.mappings().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Ownership check: must equal caller customer_id
    if str(order["customer_id"]) != customer_id:
        raise HTTPException(status_code=403, detail="Customer does not own this order.")

    # Status check: only delivered orders are returnable
    if order["status"] != "delivered":
        raise HTTPException(
            status_code=400,
            detail=f"Only orders with status 'delivered' are returnable. Current status: '{order['status']}'.",
        )

    # 2. Lock order_item row with SELECT ... FOR UPDATE so concurrent requests cannot over-return
    item_res = await session.execute(
        text("""
            SELECT id, product_id, quantity, unit_price_inr
            FROM order_items
            WHERE id = :oi_id AND order_id = :order_id
            FOR UPDATE
        """),
        {"oi_id": order_item_id, "order_id": order_id},
    )
    order_item = item_res.mappings().first()
    if not order_item:
        raise HTTPException(status_code=404, detail="Order item not found for this order.")

    # 3. Fetch product details
    prod_res = await session.execute(
        text("SELECT id, name, category, attrs FROM products WHERE id = :p_id"),
        {"p_id": order_item["product_id"]},
    )
    product = prod_res.mappings().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    category = product["category"]

    # 4. Validate return window
    in_window, deadline, window_err = check_return_window(order["delivered_at"], category)
    if not in_window:
        raise HTTPException(status_code=400, detail=window_err)

    # 5. Validate reason allowed for category
    reason_ok, reason_err = is_reason_allowed_for_category(category, reason_code)
    if not reason_ok:
        raise HTTPException(status_code=400, detail=reason_err)

    # 6. Validate photos
    photos_ok, photos_err = validate_photos(reason_code, photo_urls)
    if not photos_ok:
        raise HTTPException(status_code=400, detail=photos_err)

    # 7. Validate resolution
    res_ok, res_err = is_resolution_allowed(category, reason_code, resolution)
    if not res_ok:
        raise HTTPException(status_code=400, detail=res_err)

    # 8. Validate exchange size if exchange
    if resolution == "exchange":
        attrs = product["attrs"]
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        sz_ok, sz_err = validate_exchange_size(attrs, exchange_size)
        if not sz_ok:
            raise HTTPException(status_code=400, detail=sz_err)

    # 9. Validate quantity against returnable quantity
    ret_sum_res = await session.execute(
        text("""
            SELECT COALESCE(SUM(quantity), 0) as total_returned
            FROM return_requests
            WHERE order_item_id = :oi_id AND status NOT IN ('rejected', 'cancelled')
        """),
        {"oi_id": order_item_id},
    )
    already_returned = ret_sum_res.scalar() or 0
    available_qty = order_item["quantity"] - already_returned

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Return quantity must be greater than 0.")

    if quantity > available_qty:
        raise HTTPException(
            status_code=400,
            detail=f"Requested quantity {quantity} exceeds returnable quantity {available_qty} (Item purchased: {order_item['quantity']}, already requested/returned: {already_returned}).",
        )

    # 10. Generate unique reference
    reference = generate_return_reference()
    for _ in range(5):
        existing = await session.execute(
            text("SELECT id FROM return_requests WHERE reference = :ref"),
            {"ref": reference},
        )
        if not existing.scalar():
            break
        reference = generate_return_reference()

    # 11. Calculate refund amount preview
    unit_price = Decimal(str(order_item["unit_price_inr"]))
    refund_amount = unit_price * quantity

    return_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 12. Insert return_requests
    await session.execute(
        text("""
            INSERT INTO return_requests (
                id, reference, order_id, order_item_id, product_id, customer_id,
                quantity, reason_code, description, photo_urls, resolution, exchange_size,
                status, refund_amount_inr, created_at, updated_at
            ) VALUES (
                :id, :reference, :order_id, :order_item_id, :product_id, :customer_id,
                :quantity, :reason_code, :description, CAST(:photo_urls AS jsonb), :resolution, :exchange_size,
                'requested', :refund_amount_inr, :created_at, :updated_at
            )
        """),
        {
            "id": return_id,
            "reference": reference,
            "order_id": order_id,
            "order_item_id": order_item_id,
            "product_id": order_item["product_id"],
            "customer_id": customer_id,
            "quantity": quantity,
            "reason_code": reason_code,
            "description": description,
            "photo_urls": json.dumps(photo_urls),
            "resolution": resolution,
            "exchange_size": exchange_size if resolution == "exchange" else None,
            "refund_amount_inr": refund_amount,
            "created_at": now,
            "updated_at": now,
        },
    )

    # 13. Insert return_status_history
    await session.execute(
        text("""
            INSERT INTO return_status_history (id, return_id, status, note, actor, created_at)
            VALUES (:id, :return_id, 'requested', 'Return requested by customer', 'customer', :created_at)
        """),
        {
            "id": uuid.uuid4(),
            "return_id": return_id,
            "created_at": now,
        },
    )

    # 14. Insert outbox event
    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "return.requested",
        "return_id": str(return_id),
        "reference": reference,
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "product_id": str(order_item["product_id"]),
        "product_name": product["name"],
        "quantity": quantity,
        "reason_code": reason_code,
        "resolution": resolution,
        "exchange_size": exchange_size,
        "status": "requested",
        "refund_amount_inr": float(refund_amount),
        "occurred_at": now.isoformat(),
    }

    await session.execute(
        text("""
            INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
            VALUES (:id, 'returns.events', :key, CAST(:payload AS jsonb), NOW(), NULL)
        """),
        {
            "id": uuid.uuid4(),
            "key": str(return_id),
            "payload": json.dumps(event_payload),
        },
    )

    return {
        "id": str(return_id),
        "reference": reference,
        "order_id": str(order_id),
        "order_item_id": str(order_item_id),
        "product_id": str(order_item["product_id"]),
        "product_name": product["name"],
        "quantity": quantity,
        "reason_code": reason_code,
        "resolution": resolution,
        "exchange_size": exchange_size,
        "status": "requested",
        "refund_amount_inr": float(refund_amount),
        "photo_urls": photo_urls,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


async def cancel_return_request(
    session: AsyncSession,
    return_id: str,
    customer_id: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Customer cancels a return from requested or approved status."""
    # Verify return exists and ownership
    res = await session.execute(
        text("SELECT id, reference, order_id, customer_id, product_id, quantity, reason_code, resolution, status, refund_amount_inr FROM return_requests WHERE id = :id FOR UPDATE"),
        {"id": return_id},
    )
    ret = res.mappings().first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found.")

    if str(ret["customer_id"]) != customer_id:
        raise HTTPException(status_code=403, detail="Customer does not own this return request.")

    if ret["status"] not in ["requested", "approved"]:
        raise HTTPException(
            status_code=409,
            detail=f"Return request cannot be cancelled in status '{ret['status']}'. Only 'requested' or 'approved' returns can be cancelled.",
        )

    # Atomic guarded update
    update_res = await session.execute(
        text("""
            UPDATE return_requests
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = :id AND status IN ('requested', 'approved')
        """),
        {"id": return_id},
    )
    if update_res.rowcount == 0:
        raise HTTPException(status_code=409, detail="Concurrent update conflict: status changed.")

    now = datetime.now(timezone.utc)
    cancel_note = note or "Cancelled by customer"

    # Status history
    await session.execute(
        text("""
            INSERT INTO return_status_history (id, return_id, status, note, actor, created_at)
            VALUES (:id, :return_id, 'cancelled', :note, 'customer', :created_at)
        """),
        {"id": uuid.uuid4(), "return_id": return_id, "note": cancel_note, "created_at": now},
    )

    # Outbox event
    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "return.cancelled",
        "return_id": str(return_id),
        "reference": ret["reference"],
        "order_id": str(ret["order_id"]),
        "customer_id": str(ret["customer_id"]),
        "product_id": str(ret["product_id"]),
        "quantity": ret["quantity"],
        "reason_code": ret["reason_code"],
        "resolution": ret["resolution"],
        "status": "cancelled",
        "refund_amount_inr": float(ret["refund_amount_inr"]) if ret["refund_amount_inr"] is not None else 0.0,
        "occurred_at": now.isoformat(),
    }

    await session.execute(
        text("""
            INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
            VALUES (:id, 'returns.events', :key, CAST(:payload AS jsonb), NOW(), NULL)
        """),
        {
            "id": uuid.uuid4(),
            "key": str(return_id),
            "payload": json.dumps(event_payload),
        },
    )

    return {"status": "cancelled", "return_id": str(return_id), "reference": ret["reference"]}


async def transition_return_request(
    session: AsyncSession,
    return_id: str,
    action: str,
    note: Optional[str] = None,
    pickup_date_str: Optional[str] = None,
    item_condition: Optional[str] = None,
) -> Dict[str, Any]:
    """Admin transitions a return request according to the state machine with atomic stock & outbox updates."""
    target_status = ADMIN_ACTION_MAP.get(action)
    if not target_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: '{action}'. Allowed actions: {list(ADMIN_ACTION_MAP.keys())}",
        )

    # Lock return_request row
    res = await session.execute(
        text("""
            SELECT r.*, o.city, oi.unit_price_inr
            FROM return_requests r
            JOIN orders o ON o.id = r.order_id
            JOIN order_items oi ON oi.id = r.order_item_id
            WHERE r.id = :id
            FOR UPDATE
        """),
        {"id": return_id},
    )
    ret = res.mappings().first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found.")

    current_status = ret["status"]

    # Verify state machine transition
    if not can_transition(current_status, target_status):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid transition from '{current_status}' to '{target_status}' via action '{action}'.",
        )

    now = datetime.now(timezone.utc)
    parsed_pickup_date: Optional[date] = None
    applied_item_condition: Optional[str] = None
    refund_amount_val: Optional[Decimal] = ret["refund_amount_inr"]
    outbox_events: List[Dict[str, Any]] = []

    # Action-specific logic
    if action == "schedule_pickup":
        if pickup_date_str:
            try:
                parsed_pickup_date = datetime.strptime(pickup_date_str.strip(), "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="pickup_date must be in YYYY-MM-DD format.")
        else:
            # Default to next day
            parsed_pickup_date = date.today() + timedelta(days=1)

    elif action == "mark_received":
        applied_item_condition = (item_condition or "resellable").strip().lower()
        if applied_item_condition not in ["resellable", "damaged"]:
            raise HTTPException(status_code=400, detail="item_condition must be 'resellable' or 'damaged'.")

        # If resellable: UPDATE store_stock SET qty = qty + :q, updated_at = NOW() WHERE product_id = :p AND city = :orders.city
        if applied_item_condition == "resellable":
            stock_up = await session.execute(
                text("""
                    UPDATE store_stock
                    SET qty = qty + :q, updated_at = NOW()
                    WHERE product_id = :p AND city = :city
                """),
                {"q": ret["quantity"], "p": ret["product_id"], "city": ret["city"]},
            )
            if stock_up.rowcount == 0:
                logger.warning(
                    "return_restock_stock_row_missing",
                    product_id=str(ret["product_id"]),
                    city=ret["city"],
                )
            else:
                # Fetch new remaining qty
                new_q_res = await session.execute(
                    text("SELECT qty FROM store_stock WHERE product_id = :p AND city = :city"),
                    {"p": ret["product_id"], "city": ret["city"]},
                )
                new_qty = new_q_res.scalar() or 0
                outbox_events.append({
                    "topic": "inventory.changed",
                    "key": str(ret["product_id"]),
                    "payload": {
                        "event_id": str(uuid.uuid4()),
                        "event_type": "inventory.changed",
                        "order_id": str(ret["order_id"]),
                        "product_id": str(ret["product_id"]),
                        "city": ret["city"],
                        "added_qty": ret["quantity"],
                        "remaining_qty": new_qty,
                    },
                })

    elif action == "issue_refund":
        if ret["resolution"] != "refund":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot issue refund for return with resolution '{ret['resolution']}'.",
            )
        refund_amount_val = Decimal(str(ret["unit_price_inr"])) * ret["quantity"]

    elif action == "ship_replacement":
        if ret["resolution"] not in ["replacement", "exchange"]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot ship replacement for return with resolution '{ret['resolution']}'.",
            )
        # Decrement stock with guarded UPDATE
        stock_down = await session.execute(
            text("""
                UPDATE store_stock
                SET qty = qty - :qty, updated_at = NOW()
                WHERE product_id = :p_id AND city = :city AND qty >= :qty
            """),
            {"qty": ret["quantity"], "p_id": ret["product_id"], "city": ret["city"]},
        )
        if stock_down.rowcount == 0:
            # Leave at 'received' so admin can choose refund
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "REPLACEMENT_UNAVAILABLE",
                    "message": f"Replacement stock unavailable for product in {ret['city']}.",
                },
            )
        new_q_res = await session.execute(
            text("SELECT qty FROM store_stock WHERE product_id = :p AND city = :city"),
            {"p": ret["product_id"], "city": ret["city"]},
        )
        new_qty = new_q_res.scalar() or 0
        outbox_events.append({
            "topic": "inventory.changed",
            "key": str(ret["product_id"]),
            "payload": {
                "event_id": str(uuid.uuid4()),
                "event_type": "inventory.changed",
                "order_id": str(ret["order_id"]),
                "product_id": str(ret["product_id"]),
                "city": ret["city"],
                "deducted_qty": ret["quantity"],
                "remaining_qty": new_qty,
            },
        })

    # Guard update return_requests
    update_res = await session.execute(
        text("""
            UPDATE return_requests
            SET status = :target,
                updated_at = :now,
                admin_note = COALESCE(:note, admin_note),
                pickup_date = COALESCE(:pickup_date, pickup_date),
                item_condition = COALESCE(:item_cond, item_condition),
                refund_amount_inr = COALESCE(:refund_amt, refund_amount_inr)
            WHERE id = :id AND status = :expected
        """),
        {
            "id": return_id,
            "target": target_status,
            "expected": current_status,
            "now": now,
            "note": note,
            "pickup_date": parsed_pickup_date,
            "item_cond": applied_item_condition,
            "refund_amt": refund_amount_val,
        },
    )
    if update_res.rowcount == 0:
        raise HTTPException(status_code=409, detail="Concurrent transition conflict: status already modified.")

    # Insert status history
    history_note = note or f"Status changed to {target_status} via admin action '{action}'"
    await session.execute(
        text("""
            INSERT INTO return_status_history (id, return_id, status, note, actor, created_at)
            VALUES (:id, :return_id, :status, :note, 'admin', :created_at)
        """),
        {
            "id": uuid.uuid4(),
            "return_id": return_id,
            "status": target_status,
            "note": history_note,
            "created_at": now,
        },
    )

    # Primary returns event
    event_type = f"return.{target_status}"
    if action == "issue_refund":
        event_type = "refund.issued"

    outbox_events.append({
        "topic": "returns.events",
        "key": str(return_id),
        "payload": {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "return_id": str(return_id),
            "reference": ret["reference"],
            "order_id": str(ret["order_id"]),
            "customer_id": str(ret["customer_id"]),
            "product_id": str(ret["product_id"]),
            "quantity": ret["quantity"],
            "reason_code": ret["reason_code"],
            "resolution": ret["resolution"],
            "status": target_status,
            "refund_amount_inr": float(refund_amount_val) if refund_amount_val is not None else 0.0,
            "occurred_at": now.isoformat(),
        },
    })

    # Insert all outbox events in the same transaction
    for ev in outbox_events:
        await session.execute(
            text("""
                INSERT INTO outbox (id, topic, key, payload, created_at, published_at)
                VALUES (:id, :topic, :key, CAST(:payload AS jsonb), NOW(), NULL)
            """),
            {
                "id": uuid.uuid4(),
                "topic": ev["topic"],
                "key": ev["key"],
                "payload": json.dumps(ev["payload"]),
            },
        )

    return {
        "id": str(return_id),
        "reference": ret["reference"],
        "status": target_status,
        "previous_status": current_status,
        "action": action,
        "refund_amount_inr": float(refund_amount_val) if refund_amount_val is not None else None,
        "pickup_date": parsed_pickup_date.isoformat() if parsed_pickup_date else (ret["pickup_date"].isoformat() if ret["pickup_date"] else None),
        "item_condition": applied_item_condition or ret["item_condition"],
        "updated_at": now.isoformat(),
    }
