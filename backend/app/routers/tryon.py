"""Try-On Router — calibration, analytics, and AI try-on (Decart realtime VTON)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.database import async_session_factory

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/api/tryon", tags=["tryon"])


ALLOWED_EVENTS = [
    "tryon_started",
    "tryon_added_to_cart",
    "tryon_ai_started",
    "tryon_ai_swapped",
    "tryon_recording_started",
]

# --- AI try-on token minting -------------------------------------------------
# Simple in-memory per-IP limiter so a bot cannot burn the Decart budget.
_TOKEN_HITS: Dict[str, list] = {}
_TOKEN_LIMIT = 6        # tokens
_TOKEN_WINDOW = 60.0    # per this many seconds


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    hits = [h for h in _TOKEN_HITS.get(ip, []) if now - h < _TOKEN_WINDOW]
    if len(hits) >= _TOKEN_LIMIT:
        _TOKEN_HITS[ip] = hits
        return True
    hits.append(now)
    _TOKEN_HITS[ip] = hits
    return False


class CalibrationUpdateRequest(BaseModel):
    tryon_config: Dict[str, Any]


class TryonEventRequest(BaseModel):
    event_type: str
    product_id: str
    sku: Optional[str] = None
    tryon_type: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/calibrate/{product_id}")
async def save_calibration(product_id: str, payload: CalibrationUpdateRequest):
    """Dev calibration endpoint: saves refined scale, offsets, rotation to product."""
    async with async_session_factory() as session:
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
    if req.event_type not in ALLOWED_EVENTS:
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
    except Exception:
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
                    WHERE event_type IN ('tryon_started', 'tryon_added_to_cart', 'tryon_ai_started', 'tryon_ai_swapped')
                    GROUP BY aggregate_id, event_type
                """)
            )
            rows = res.mappings().all()
            return {"stats": [dict(r) for r in rows]}
    except Exception:
        return {"stats": []}


@router.get("/config")
async def ai_tryon_config():
    """Tells the storefront whether AI try-on is available and which model to use."""
    model_name = getattr(settings, "decart_vton_model", "lucy-vton-latest")
    if not model_name or model_name == "vton-1":
        model_name = "lucy-vton-latest"
    return {
        "ai_enabled": bool(getattr(settings, "decart_api_key", None)),
        "model": model_name,
        "maxSessionSeconds": getattr(settings, "ai_tryon_max_seconds", 120),
    }


@router.post("/token")
async def create_ai_tryon_token(request: Request):
    """Mint a short-lived Decart client token. The permanent key never leaves the server."""
    api_key = getattr(settings, "decart_api_key", None)
    if not api_key:
        raise HTTPException(status_code=503, detail="AI try-on is not configured on this server.")
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many try-on requests. Please wait a minute.")

    try:
        from decart import DecartClient
    except ImportError:
        raise HTTPException(status_code=503, detail="The 'decart' package is not installed.")

    max_secs = getattr(settings, "ai_tryon_max_seconds", 120)
    allowed_origins_str = getattr(settings, "ai_tryon_allowed_origins", "")
    kwargs: Dict[str, Any] = {
        "expires_in": 60,
        "constraints": {"realtime": {"maxSessionDuration": max_secs}},
    }
    origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]
    if origins:
        kwargs["allowed_origins"] = origins

    try:
        async with DecartClient(api_key=api_key) as client:
            token = await client.tokens.create(**kwargs)
    except Exception as exc:
        logger.error("decart_token_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Could not start an AI try-on session.")

    return {
        "apiKey": token.api_key,
        "expiresAt": str(getattr(token, "expires_at", "")),
        "maxSessionSeconds": max_secs,
    }
