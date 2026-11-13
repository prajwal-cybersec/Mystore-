"""Pipeline and notifications router providing Server-Sent Events (SSE) stream,
pipeline status snapshot, and customer notification list.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_factory
from app.consumers.analytics_consumer import get_analytics_snapshot

router = APIRouter(tags=["pipeline"])
logger = structlog.stdlib.get_logger(__name__)


@router.get("/notifications")
async def list_notifications(
    order_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Fetch notifications (SMS / EMAIL) for recent orders."""
    query = "SELECT id, order_id, type, channel, message, created_at FROM notifications"
    params: Dict[str, Any] = {"limit": limit}

    if order_id:
        query += " WHERE order_id = :oid"
        params["oid"] = uuid.UUID(order_id)

    query += " ORDER BY created_at DESC LIMIT :limit"
    res = await db.execute(text(query), params)
    rows = res.mappings().all()

    return [
        {
            "id": str(r["id"]),
            "order_id": str(r["order_id"]),
            "type": r["type"],
            "channel": r["channel"],
            "message": r["message"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/pipeline/status")
async def pipeline_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Provide real-time status counts across outbox, processed_events, and notifications."""
    outbox_pending = await db.execute(text("SELECT count(*) FROM outbox WHERE published_at IS NULL"))
    outbox_published = await db.execute(text("SELECT count(*) FROM outbox WHERE published_at IS NOT NULL"))
    events_processed = await db.execute(text("SELECT count(*) FROM processed_events"))
    total_notifications = await db.execute(text("SELECT count(*) FROM notifications"))
    total_orders = await db.execute(text("SELECT count(*) FROM orders"))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "orders": total_orders.scalar() or 0,
            "outbox_pending": outbox_pending.scalar() or 0,
            "outbox_published": outbox_published.scalar() or 0,
            "events_processed": events_processed.scalar() or 0,
            "notifications_sent": total_notifications.scalar() or 0,
        },
        "analytics": get_analytics_snapshot(),
    }


async def event_generator() -> AsyncGenerator[str, None]:
    """Emit Server-Sent Events showing live stages of orders, outbox, and consumer events."""
    last_checked_time = datetime.now(timezone.utc)
    
    # Send initial connected ping
    init_data = json.dumps({
        "stage": "CONNECTED",
        "message": "MyStore Event Stream connected",
        "timestamp": last_checked_time.isoformat(),
    })
    yield f"data: {init_data}\n\n"

    while True:
        try:
            async with async_session_factory() as session:
                # Check recent outbox records
                res = await session.execute(
                    text("""
                        SELECT id, topic, key, payload, created_at, published_at
                        FROM outbox
                        WHERE created_at >= NOW() - INTERVAL '30 seconds'
                        ORDER BY created_at DESC
                        LIMIT 5
                    """)
                )
                rows = res.mappings().all()
                for r in rows:
                    event_data = {
                        "id": str(r["id"]),
                        "topic": r["topic"],
                        "key": str(r["key"]),
                        "published": r["published_at"] is not None,
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                        "stage": "OUTBOX_PUBLISHED" if r["published_at"] else "OUTBOX_PENDING",
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("sse_stream_error", error=str(exc))
            await asyncio.sleep(2.0)


@router.get("/pipeline/stream")
async def pipeline_stream():
    """Server-Sent Events endpoint emitting live order stage transitions:
    placed -> outbox published -> Kafka consumed -> inventory updated -> OpenSearch re-indexed.
    """
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

