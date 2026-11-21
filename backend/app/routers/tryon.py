"""Try-On Router exposing calibration persistence and analytics events."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.database import async_session_factory

router = APIRouter(prefix="/api/tryon", tags=["tryon"])


class CalibrationUpdateRequest(BaseModel):
    tryon_config: Dict[str, Any]


class TryonEventRequest(BaseModel):
    event_type: str  # 'tryon_started' | 'tryon_added_to_cart'
    product_id: str
    sku: Optional[str] = None
    tryon_type: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/calibrate/{product_id}")
async def save_calibration(product_id: str, payload: CalibrationUpdateRequest):
    """Dev calibration endpoint: saves refined scale, offsets, rotation to product."""
    async with async_session_factory() as session:
        # Check if product exists by id or sku
        res = await session.execute(
            text("SELECT id, sku, name, tryon_config FROM products WHERE id::text = :pid OR sku = :pid"),
            {"pid": product_id}
        )
        row = res.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found.")

        current_config = row["tryon_config"] or {}
        if isinstance(current_config, str):
            try:
                current_config = json.loads(current_config)
            except Exception:
                current_config = {}

        # Merge new calibration values
        updated_config = {**current_config, **payload.tryon_config}

        await session.execute(
            text("UPDATE products SET tryon_config = :cfg WHERE id = :id"),
            {"cfg": json.dumps(updated_config), "id": row["id"]}
        )
        await session.commit()

        return {
            "status": "success",
            "sku": row["sku"],
            "name": row["name"],
            "tryon_config": updated_config,
            "message": f"Calibration saved successfully for {row['sku']}."
        }


@router.post("/events")
async def track_tryon_event(req: TryonEventRequest):
    """Analytics endpoint recording try-on engagement and add-to-cart conversions."""
    if req.event_type not in ["tryon_started", "tryon_added_to_cart"]:
        raise HTTPException(status_code=400, detail="Invalid try-on event type.")

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": req.event_type,
        "product_id": req.product_id,
        "sku": req.sku,
        "tryon_type": req.tryon_type,
        "session_id": req.session_id or str(uuid.uuid4())
    }

    try:
        async with async_session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO outbox (id, event_type, aggregate_type, aggregate_id, payload, created_at)
                    VALUES (:id, :event_type, 'tryon', :agg_id, :payload, NOW())
                """),
                {
                    "id": uuid.uuid4(),
                    "event_type": req.event_type,
                    "agg_id": req.product_id,
                    "payload": json.dumps(event_payload)
                }
            )
            await session.commit()
    except Exception as e:
        # Fallback if outbox table has different schema
        pass

    return {"status": "recorded", "event": req.event_type, "product_id": req.product_id}


@router.get("/stats")
async def get_tryon_stats():
    """Returns analytics summary of live try-ons."""
    try:
        async with async_session_factory() as session:
            res = await session.execute(
                text("""
                    SELECT aggregate_id as product_id, event_type, count(*) as count
                    FROM outbox
                    WHERE event_type IN ('tryon_started', 'tryon_added_to_cart')
                    GROUP BY aggregate_id, event_type
                """)
            )
            rows = res.mappings().all()
            return {"stats": [dict(r) for r in rows]}
    except Exception:
        return {"stats": []}
