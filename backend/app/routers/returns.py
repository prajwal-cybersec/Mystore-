"""Returns router handling customer return requests, uploads, order histories, admin state transitions, and dev order progression."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.returns_policy import (
    ADMIN_ACTION_MAP,
    CATEGORY_RETURN_WINDOWS,
    DELIVERY_LIFECYCLE,
    REASONS,
    RESOLUTIONS,
    TRANSITIONS,
    check_return_window,
    get_category_window_days,
)
from app.returns_service import (
    cancel_return_request,
    create_return_request,
    transition_return_request,
)

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(tags=["returns"])

# Ensure uploads directory exists
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "returns"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"


# --- Dependency: Admin Auth ---
def verify_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> str:
    if not settings.admin_api_key or not settings.admin_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured on the server.",
        )
    if not x_admin_key or x_admin_key.strip() != settings.admin_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing X-Admin-Key header.",
        )
    return x_admin_key


# --- Schemas ---
class ReturnCreateRequest(BaseModel):
    customer_id: str = Field(default=DEFAULT_CUSTOMER_ID)
    order_item_id: str
    quantity: int = Field(gt=0)
    reason_code: str
    description: Optional[str] = None
    photo_urls: List[str] = Field(default_factory=list)
    resolution: str  # refund | replacement | exchange
    exchange_size: Optional[str] = None


class ReturnCancelRequest(BaseModel):
    customer_id: str = Field(default=DEFAULT_CUSTOMER_ID)
    note: Optional[str] = None


class AdminTransitionRequest(BaseModel):
    action: str
    note: Optional[str] = None
    pickup_date: Optional[str] = None
    item_condition: Optional[str] = None


class DevAdvanceRequest(BaseModel):
    target_status: Optional[str] = None


# --- Policy Endpoint ---
@router.get("/api/returns/policy")
async def get_returns_policy():
    """Return reasons, resolutions, category windows, and transitions."""
    return {
        "reasons": REASONS,
        "resolutions": RESOLUTIONS,
        "category_windows": CATEGORY_RETURN_WINDOWS,
        "transitions": TRANSITIONS,
        "delivery_lifecycle": DELIVERY_LIFECYCLE,
    }


# --- Customer Orders & Ineligibility Calculations ---
@router.get("/api/orders")
async def list_customer_orders(
    customer_id: str = Query(default=DEFAULT_CUSTOMER_ID),
    session: AsyncSession = Depends(get_db),
):
    """List orders newest first with detailed item-level return eligibility."""
    # 1. Fetch orders
    orders_res = await session.execute(
        text("""
            SELECT id, customer_id, city, status, total_inr, created_at, delivered_at
            FROM orders
            WHERE customer_id = :cid
            ORDER BY created_at DESC
        """),
        {"cid": customer_id},
    )
    orders = orders_res.mappings().all()

    if not orders:
        return {"orders": []}

    order_ids = [str(o["id"]) for o in orders]

    # 2. Fetch items for all these orders
    items_res = await session.execute(
        text("""
            SELECT oi.id as order_item_id, oi.order_id, oi.product_id, oi.quantity, oi.unit_price_inr,
                   p.name, p.image_url, p.category, p.attrs
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ANY(:oids::uuid[])
        """),
        {"oids": order_ids},
    )
    all_items = items_res.mappings().all()

    # 3. Fetch return requests for these orders
    returns_res = await session.execute(
        text("""
            SELECT id, reference, order_id, order_item_id, product_id, quantity,
                   reason_code, resolution, status, refund_amount_inr, exchange_size,
                   pickup_date, item_condition, created_at, updated_at
            FROM return_requests
            WHERE order_id = ANY(:oids::uuid[])
            ORDER BY created_at DESC
        """),
        {"oids": order_ids},
    )
    all_returns = returns_res.mappings().all()

    # Group items and returns by order_id
    items_by_order: Dict[str, List[Any]] = {oid: [] for oid in order_ids}
    returns_by_item: Dict[str, List[Any]] = {}
    returns_by_order: Dict[str, List[Any]] = {oid: [] for oid in order_ids}

    for r in all_returns:
        ret_dict = dict(r)
        ret_dict["id"] = str(ret_dict["id"])
        ret_dict["order_id"] = str(ret_dict["order_id"])
        ret_dict["order_item_id"] = str(ret_dict["order_item_id"])
        ret_dict["product_id"] = str(ret_dict["product_id"])
        ret_dict["created_at"] = ret_dict["created_at"].isoformat() if ret_dict["created_at"] else None
        ret_dict["updated_at"] = ret_dict["updated_at"].isoformat() if ret_dict["updated_at"] else None
        ret_dict["pickup_date"] = ret_dict["pickup_date"].isoformat() if ret_dict["pickup_date"] else None
        ret_dict["refund_amount_inr"] = float(ret_dict["refund_amount_inr"]) if ret_dict["refund_amount_inr"] is not None else None

        returns_by_order[ret_dict["order_id"]].append(ret_dict)
        returns_by_item.setdefault(ret_dict["order_item_id"], []).append(ret_dict)

    result_orders = []
    now = datetime.now(timezone.utc)

    for o in orders:
        oid = str(o["id"])
        is_delivered = o["status"] == "delivered"
        delivered_at = o["delivered_at"]

        order_items_list = []
        for it in all_items:
            if str(it["order_id"]) != oid:
                continue

            item_id = str(it["order_item_id"])
            item_returns = returns_by_item.get(item_id, [])

            # Active/pending/accepted returns sum
            active_returned_qty = sum(
                r["quantity"] for r in item_returns if r["status"] not in ["rejected", "cancelled"]
            )
            returnable_qty = max(0, it["quantity"] - active_returned_qty)

            # Check eligibility
            return_eligible = False
            return_deadline = None
            ineligible_reason = None

            if not is_delivered:
                ineligible_reason = f"Order status is '{o['status']}'. Items can only be returned after delivery."
            elif returnable_qty <= 0:
                ineligible_reason = "All units of this item have already been returned or requested for return."
            else:
                in_window, deadline, window_msg = check_return_window(delivered_at, it["category"])
                if deadline:
                    return_deadline = deadline.isoformat()
                if not in_window:
                    ineligible_reason = window_msg
                else:
                    return_eligible = True

            # Parse attrs for available sizes if fashion
            attrs = it["attrs"]
            if isinstance(attrs, str):
                try:
                    attrs = json.loads(attrs)
                except Exception:
                    attrs = {}
            sizes = attrs.get("sizes", []) if isinstance(attrs, dict) else []

            order_items_list.append({
                "order_item_id": item_id,
                "product_id": str(it["product_id"]),
                "name": it["name"],
                "image_url": it["image_url"],
                "category": it["category"],
                "quantity": it["quantity"],
                "unit_price_inr": float(it["unit_price_inr"]),
                "returnable_qty": returnable_qty,
                "return_eligible": return_eligible,
                "return_deadline": return_deadline,
                "ineligible_reason": ineligible_reason,
                "sizes": sizes,
                "returns": item_returns,
            })

        result_orders.append({
            "id": oid,
            "customer_id": str(o["customer_id"]),
            "city": o["city"],
            "status": o["status"],
            "total_inr": float(o["total_inr"]),
            "created_at": o["created_at"].isoformat() if o["created_at"] else None,
            "delivered_at": delivered_at.isoformat() if delivered_at else None,
            "items": order_items_list,
            "returns": returns_by_order.get(oid, []),
        })

    return {"orders": result_orders}


# --- Image Upload ---
@router.post("/api/returns/uploads")
async def upload_return_image(file: UploadFile = File(...)):
    """Upload photo for return proof (JPEG/PNG/WEBP, <= 2MB). Note: Render filesystem is ephemeral."""
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    content_type = file.content_type or ""
    if content_type.lower() not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{content_type}'. Only JPEG, PNG, and WebP images are allowed.",
        )

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds 2 MB limit ({len(content)} bytes).",
        )

    ext = allowed_types[content_type.lower()]
    filename = f"{uuid.uuid4()}{ext}"
    target_path = UPLOAD_DIR / filename

    with open(target_path, "wb") as f:
        f.write(content)

    return {"url": f"/static/uploads/returns/{filename}"}


# --- Create Return Request ---
@router.post("/api/orders/{order_id}/returns", status_code=status.HTTP_201_CREATED)
async def submit_return(
    order_id: str,
    payload: ReturnCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Raise a return request for an order item with concurrency lock & outbox event."""
    result = await create_return_request(
        session=session,
        order_id=order_id,
        customer_id=payload.customer_id,
        order_item_id=payload.order_item_id,
        quantity=payload.quantity,
        reason_code=payload.reason_code,
        resolution=payload.resolution,
        description=payload.description,
        photo_urls=payload.photo_urls,
        exchange_size=payload.exchange_size,
    )
    await session.commit()
    return result


# --- List / Get Returns ---
@router.get("/api/returns")
async def list_returns(
    customer_id: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """List returns with filtering by customer_id and/or order_id."""
    query = """
        SELECT r.id, r.reference, r.order_id, r.order_item_id, r.product_id, r.customer_id,
               r.quantity, r.reason_code, r.description, r.photo_urls, r.resolution,
               r.exchange_size, r.status, r.item_condition, r.refund_amount_inr,
               r.pickup_date, r.admin_note, r.created_at, r.updated_at,
               p.name as product_name, p.image_url as product_image_url, p.category,
               o.city
        FROM return_requests r
        JOIN products p ON p.id = r.product_id
        JOIN orders o ON o.id = r.order_id
        WHERE 1=1
    """
    params: Dict[str, Any] = {}
    if customer_id:
        query += " AND r.customer_id = :cid"
        params["cid"] = customer_id
    if order_id:
        query += " AND r.order_id = :oid"
        params["oid"] = order_id

    query += " ORDER BY r.created_at DESC"

    res = await session.execute(text(query), params)
    rows = res.mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["order_id"] = str(d["order_id"])
        d["order_item_id"] = str(d["order_item_id"])
        d["product_id"] = str(d["product_id"])
        d["customer_id"] = str(d["customer_id"])
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
        d["updated_at"] = d["updated_at"].isoformat() if d["updated_at"] else None
        d["pickup_date"] = d["pickup_date"].isoformat() if d["pickup_date"] else None
        d["refund_amount_inr"] = float(d["refund_amount_inr"]) if d["refund_amount_inr"] is not None else None
        items.append(d)

    return {"returns": items}


# --- Analytics & Stats ---
@router.get("/api/returns/stats")
async def get_returns_stats(session: AsyncSession = Depends(get_db)):
    """Aggregate returns metrics, top reasons, and Try-On vs Non-Try-On comparison."""
    # 1. Total returns count & by_status
    counts_res = await session.execute(
        text("""
            SELECT status, COUNT(*) as cnt
            FROM return_requests
            GROUP BY status
        """)
    )
    by_status = {row["status"]: row["cnt"] for row in counts_res.mappings().all()}
    total_returns = sum(by_status.values())

    # 2. Total orders count
    orders_cnt_res = await session.execute(text("SELECT COUNT(*) FROM orders"))
    total_orders = orders_cnt_res.scalar() or 0

    return_rate = round((total_returns / total_orders * 100), 2) if total_orders > 0 else 0.0

    # 3. Top 5 return reasons
    reasons_res = await session.execute(
        text("""
            SELECT reason_code, COUNT(*) as cnt
            FROM return_requests
            GROUP BY reason_code
            ORDER BY cnt DESC
            LIMIT 5
        """)
    )
    top_reasons = [{"reason": row["reason_code"], "count": row["cnt"]} for row in reasons_res.mappings().all()]

    # 4. Try-on comparison
    tryon_res = await session.execute(
        text("""
            SELECT 
                COUNT(DISTINCT r.id) FILTER (WHERE te.product_id IS NOT NULL) as tryon_returns,
                COUNT(DISTINCT r.id) FILTER (WHERE te.product_id IS NULL) as non_tryon_returns
            FROM return_requests r
            LEFT JOIN tryon_events te ON te.product_id = r.product_id
        """)
    )
    tryon_row = tryon_res.mappings().first()
    tryon_returns = tryon_row["tryon_returns"] if tryon_row else 0
    non_tryon_returns = tryon_row["non_tryon_returns"] if tryon_row else 0

    # Total ordered items with vs without tryon
    orders_items_res = await session.execute(
        text("""
            SELECT
                COUNT(DISTINCT oi.id) FILTER (WHERE te.product_id IS NOT NULL) as tryon_items_ordered,
                COUNT(DISTINCT oi.id) FILTER (WHERE te.product_id IS NULL) as non_tryon_items_ordered
            FROM order_items oi
            LEFT JOIN tryon_events te ON te.product_id = oi.product_id
        """)
    )
    items_row = orders_items_res.mappings().first()
    tryon_ordered = items_row["tryon_items_ordered"] if items_row else 0
    non_tryon_ordered = items_row["non_tryon_items_ordered"] if items_row else 0

    tryon_rate = round((tryon_returns / tryon_ordered * 100), 2) if tryon_ordered > 0 else 0.0
    non_tryon_rate = round((non_tryon_returns / non_tryon_ordered * 100), 2) if non_tryon_ordered > 0 else 0.0

    return {
        "total_returns": total_returns,
        "total_orders": total_orders,
        "return_rate_pct": return_rate,
        "by_status": by_status,
        "top_reasons": top_reasons,
        "tryon_comparison": {
            "tryon_items_ordered": tryon_ordered,
            "tryon_returns": tryon_returns,
            "tryon_return_rate_pct": tryon_rate,
            "non_tryon_items_ordered": non_tryon_ordered,
            "non_tryon_returns": non_tryon_returns,
            "non_tryon_return_rate_pct": non_tryon_rate,
        },
    }


@router.get("/api/returns/{return_id}")
async def get_return_detail(
    return_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Get single return detail including timeline history."""
    res = await session.execute(
        text("""
            SELECT r.*, p.name as product_name, p.image_url as product_image_url, p.category,
                   o.city, oi.unit_price_inr
            FROM return_requests r
            JOIN products p ON p.id = r.product_id
            JOIN orders o ON o.id = r.order_id
            JOIN order_items oi ON oi.id = r.order_item_id
            WHERE r.id = :id
        """),
        {"id": return_id},
    )
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Return request not found.")

    # Fetch status history timeline
    hist_res = await session.execute(
        text("""
            SELECT id, status, note, actor, created_at
            FROM return_status_history
            WHERE return_id = :id
            ORDER BY created_at ASC
        """),
        {"id": return_id},
    )
    hist_rows = hist_res.mappings().all()

    d = dict(row)
    d["id"] = str(d["id"])
    d["order_id"] = str(d["order_id"])
    d["order_item_id"] = str(d["order_item_id"])
    d["product_id"] = str(d["product_id"])
    d["customer_id"] = str(d["customer_id"])
    d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
    d["updated_at"] = d["updated_at"].isoformat() if d["updated_at"] else None
    d["pickup_date"] = d["pickup_date"].isoformat() if d["pickup_date"] else None
    d["refund_amount_inr"] = float(d["refund_amount_inr"]) if d["refund_amount_inr"] is not None else None
    d["unit_price_inr"] = float(d["unit_price_inr"]) if d["unit_price_inr"] is not None else None

    d["history"] = [
        {
            "id": str(h["id"]),
            "status": h["status"],
            "note": h["note"],
            "actor": h["actor"],
            "created_at": h["created_at"].isoformat() if h["created_at"] else None,
        }
        for h in hist_rows
    ]

    return d


# --- Cancel Return ---
@router.post("/api/returns/{return_id}/cancel")
async def cancel_return(
    return_id: str,
    payload: ReturnCancelRequest,
    session: AsyncSession = Depends(get_db),
):
    """Customer cancels return request from requested or approved status."""
    res = await cancel_return_request(
        session=session,
        return_id=return_id,
        customer_id=payload.customer_id,
        note=payload.note,
    )
    await session.commit()
    return res


# --- Admin Endpoints ---
@router.get("/api/admin/returns")
async def admin_list_returns(
    status_filter: Optional[str] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(verify_admin_key),
):
    """Admin view: list all returns with product, customer, and order details."""
    query = """
        SELECT r.id, r.reference, r.order_id, r.order_item_id, r.product_id, r.customer_id,
               r.quantity, r.reason_code, r.description, r.photo_urls, r.resolution,
               r.exchange_size, r.status, r.item_condition, r.refund_amount_inr,
               r.pickup_date, r.admin_note, r.created_at, r.updated_at,
               p.name as product_name, p.image_url as product_image_url, p.category,
               c.name as customer_name, c.email as customer_email, c.phone as customer_phone,
               o.city, oi.unit_price_inr
        FROM return_requests r
        JOIN products p ON p.id = r.product_id
        JOIN customers c ON c.id = r.customer_id
        JOIN orders o ON o.id = r.order_id
        JOIN order_items oi ON oi.id = r.order_item_id
        WHERE 1=1
    """
    params: Dict[str, Any] = {}
    if status_filter:
        query += " AND r.status = :st"
        params["st"] = status_filter

    query += " ORDER BY r.created_at DESC"

    res = await session.execute(text(query), params)
    rows = res.mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["order_id"] = str(d["order_id"])
        d["order_item_id"] = str(d["order_item_id"])
        d["product_id"] = str(d["product_id"])
        d["customer_id"] = str(d["customer_id"])
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None
        d["updated_at"] = d["updated_at"].isoformat() if d["updated_at"] else None
        d["pickup_date"] = d["pickup_date"].isoformat() if d["pickup_date"] else None
        d["refund_amount_inr"] = float(d["refund_amount_inr"]) if d["refund_amount_inr"] is not None else None
        d["unit_price_inr"] = float(d["unit_price_inr"]) if d["unit_price_inr"] is not None else None
        items.append(d)

    return {"returns": items}


@router.post("/api/admin/returns/{return_id}/transition")
async def admin_transition(
    return_id: str,
    payload: AdminTransitionRequest,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(verify_admin_key),
):
    """Admin transitions return request state with atomic inventory & outbox publishing."""
    res = await transition_return_request(
        session=session,
        return_id=return_id,
        action=payload.action,
        note=payload.note,
        pickup_date_str=payload.pickup_date,
        item_condition=payload.item_condition,
    )
    await session.commit()
    return res


# --- Dev Order Advancement ---
@router.post("/dev/orders/{order_id}/advance")
async def dev_advance_order(
    order_id: str,
    payload: Optional[DevAdvanceRequest] = None,
    session: AsyncSession = Depends(get_db),
):
    """Dev helper to simulate order delivery lifecycle: placed -> shipped -> out_for_delivery -> delivered."""
    if settings.app_env.lower() == "production":
        raise HTTPException(status_code=403, detail="Dev endpoints are disabled in production.")

    res = await session.execute(
        text("SELECT id, status, delivered_at FROM orders WHERE id = :id FOR UPDATE"),
        {"id": order_id},
    )
    order = res.mappings().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    current_status = order["status"]
    target_status = payload.target_status if payload and payload.target_status else None

    if not target_status:
        # Step sequentially through lifecycle
        if current_status in DELIVERY_LIFECYCLE:
            idx = DELIVERY_LIFECYCLE.index(current_status)
            if idx < len(DELIVERY_LIFECYCLE) - 1:
                target_status = DELIVERY_LIFECYCLE[idx + 1]
            else:
                target_status = "delivered"
        else:
            target_status = "shipped"

    if target_status not in DELIVERY_LIFECYCLE:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target status '{target_status}'. Must be one of {DELIVERY_LIFECYCLE}",
        )

    now = datetime.now(timezone.utc)
    set_delivered = (target_status == "delivered")

    await session.execute(
        text("""
            UPDATE orders
            SET status = :st,
                delivered_at = CASE WHEN :set_del = TRUE THEN COALESCE(delivered_at, :now) ELSE delivered_at END
            WHERE id = :id
        """),
        {"st": target_status, "set_del": set_delivered, "now": now, "id": order_id},
    )
    await session.commit()

    return {
        "order_id": order_id,
        "previous_status": current_status,
        "current_status": target_status,
        "delivered_at": now.isoformat() if set_delivered else (order["delivered_at"].isoformat() if order["delivered_at"] else None),
    }

