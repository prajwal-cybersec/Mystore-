"""Checkout & Orders router exposing POST /checkout, GET /orders/{id}, and POST /dev/stress-last-unit."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_factory
from app.checkout_service import execute_checkout_transaction

router = APIRouter(tags=["checkout"])


class CheckoutItemSchema(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)


class CheckoutRequestSchema(BaseModel):
    customer_id: str = "11111111-1111-1111-1111-111111111111"
    city: str = "Bengaluru"
    items: List[CheckoutItemSchema]


class StressTestRequestSchema(BaseModel):
    product_id: Optional[str] = None
    city: str = "Bengaluru"
    concurrency: int = Field(default=10, ge=2, le=50)


@router.post("/checkout")
async def checkout_endpoint(
    req: CheckoutRequestSchema,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Execute checkout in one strict atomic PostgreSQL transaction."""
    items_dicts = [{"product_id": it.product_id, "quantity": it.quantity} for it in req.items]
    async with db.begin():
        return await execute_checkout_transaction(
            session=db,
            customer_id=req.customer_id,
            city=req.city,
            items=items_dicts,
        )


@router.get("/orders/{order_id}")
async def get_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve an order and its order items."""
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order UUID")

    res = await db.execute(
        text("SELECT id, customer_id, city, status, total_inr, created_at FROM orders WHERE id = :oid"),
        {"oid": oid},
    )
    order = res.mappings().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items_res = await db.execute(
        text("""
            SELECT oi.id, oi.product_id, oi.quantity, oi.unit_price_inr, p.name as product_name, p.sku
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = :oid
        """),
        {"oid": oid},
    )
    items = items_res.mappings().all()

    return {
        "id": str(order["id"]),
        "customer_id": str(order["customer_id"]),
        "city": order["city"],
        "status": order["status"],
        "total_inr": float(order["total_inr"]),
        "created_at": order["created_at"].isoformat() if order["created_at"] else None,
        "items": [
            {
                "product_id": str(i["product_id"]),
                "product_name": i["product_name"],
                "sku": i["sku"],
                "quantity": i["quantity"],
                "unit_price_inr": float(i["unit_price_inr"]),
            }
            for i in items
        ],
    }


@router.post("/dev/stress-last-unit")
async def stress_last_unit_endpoint(
    req: StressTestRequestSchema = StressTestRequestSchema(),
) -> Dict[str, Any]:
    """Fires N concurrent checkout requests for exactly 1 remaining unit.
    Proves that two buyers can NEVER both get the last unit under race conditions.
    """
    target_city = req.city
    target_product_id = req.product_id

    # 1. If not specified, target EL-SAM-002 (seeded with exactly 1 unit in Bengaluru)
    async with async_session_factory() as session:
        if not target_product_id:
            res = await session.execute(
                text("SELECT id FROM products WHERE sku = 'EL-SAM-002'")
            )
            target_product_id = str(res.scalar_one())

        # Reset stock to exactly 1 unit for the test
        await session.execute(
            text("""
                INSERT INTO store_stock (product_id, city, qty, updated_at)
                VALUES (:pid, :city, 1, NOW())
                ON CONFLICT (product_id, city) DO UPDATE SET qty = 1, updated_at = NOW()
            """),
            {"pid": target_product_id, "city": target_city},
        )
        await session.commit()

    # 2. Fire N concurrent checkout tasks
    concurrency = req.concurrency
    successes = []
    rejections = []

    async def attempt_checkout(buyer_idx: int):
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    res = await execute_checkout_transaction(
                        session=session,
                        customer_id="11111111-1111-1111-1111-111111111111",
                        city=target_city,
                        items=[{"product_id": target_product_id, "quantity": 1}],
                    )
                    return {"status": "SUCCESS", "buyer": buyer_idx, "order_id": res["order_id"]}
        except Exception as exc:
            return {"status": "REJECTED", "buyer": buyer_idx, "reason": str(exc)}

    tasks = [attempt_checkout(i + 1) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r["status"] == "SUCCESS":
            successes.append(r)
        else:
            rejections.append(r)

    # Verify final remaining stock in DB is 0
    async with async_session_factory() as session:
        final_stock_res = await session.execute(
            text("SELECT qty FROM store_stock WHERE product_id = :pid AND city = :city"),
            {"pid": target_product_id, "city": target_city},
        )
        final_stock = final_stock_res.scalar() or 0

    return {
        "concurrency_tested": concurrency,
        "succeeded_count": len(successes),
        "rejected_count": len(rejections),
        "winner": successes[0] if successes else None,
        "final_store_stock": final_stock,
        "invariant_preserved": len(successes) == 1 and final_stock == 0,
        "message": f"Exactly {len(successes)} buyer acquired the unit; {len(rejections)} rejected with OutOfStockError.",
    }

