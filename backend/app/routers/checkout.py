"""Checkout & Orders router exposing POST /checkout, GET /orders/{id}, and POST /dev/stress-last-unit."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_factory
from app.checkout_service import execute_checkout_transaction
from app.pdf_service import (
    generate_single_invoice_pdf,
    generate_order_summary_pdf,
    merge_order_invoices_pdf,
)

logger = structlog.stdlib.get_logger(__name__)
router = APIRouter(tags=["checkout"])


async def _background_generate_invoices(sub_order_ids: List[str], order_id: str):
    """Auto-generate invoices for newly created sub-orders in the background."""
    try:
        from app.invoice_service import generate_suborder_invoice
        from app.consumers.notification_consumer import handle_invoice_generated
        async with async_session_factory() as session:
            async with session.begin():
                for so_id in sub_order_ids:
                    await generate_suborder_invoice(session=session, sub_order_id=so_id)
        # Notify once all are generated
        await handle_invoice_generated({"order_id": order_id})
    except Exception as exc:
        logger.error("background_invoice_generation_failed", order_id=order_id, error=str(exc))


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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Execute checkout in one strict atomic PostgreSQL transaction."""
    items_dicts = [{"product_id": it.product_id, "quantity": it.quantity} for it in req.items]
    async with db.begin():
        res = await execute_checkout_transaction(
            session=db,
            customer_id=req.customer_id,
            city=req.city,
            items=items_dicts,
        )

    # Immediately trigger invoice generation for each sub-order in background
    sub_order_ids = [so["sub_order_id"] for so in res.get("sub_orders", [])]
    if sub_order_ids:
        background_tasks.add_task(
            _background_generate_invoices,
            sub_order_ids=sub_order_ids,
            order_id=res["order_id"],
        )

    return res


@router.get("/orders/{order_id}")
async def get_order_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve an order, including all seller sub-orders, invoices, and shipment tracking."""
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order UUID")

    res = await db.execute(
        text("""
            SELECT id, customer_id, city, status, total_inr, grand_total,
                   invoices_expected, invoices_ready, created_at
            FROM orders
            WHERE id = :oid
        """),
        {"oid": oid},
    )
    order = res.mappings().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Fetch sub-orders with sellers, invoices, and shipments
    so_res = await db.execute(
        text("""
            SELECT so.id as sub_order_id, so.order_id, so.seller_id, so.city as package_city,
                   so.subtotal, so.tax, so.status as sub_order_status, so.created_at as so_created_at,
                   s.name as seller_name, s.seller_code, s.state as seller_state, s.gstin, s.address as seller_address,
                   i.id as invoice_id, i.invoice_no, i.taxable_value, i.cgst, i.sgst, i.igst, i.total as invoice_total, i.issued_at,
                   sh.id as shipment_id, sh.tracking_number, sh.status as shipment_status
            FROM sub_orders so
            JOIN sellers s ON s.id = so.seller_id
            LEFT JOIN invoices i ON i.sub_order_id = so.id
            LEFT JOIN shipments sh ON sh.sub_order_id = so.id
            WHERE so.order_id = :oid
            ORDER BY so.created_at ASC
        """),
        {"oid": oid},
    )
    sub_orders_rows = so_res.mappings().all()

    # If any sub-orders lack invoices, generate them on-the-fly now
    missing_invoices = [so for so in sub_orders_rows if not so["invoice_no"]]
    if missing_invoices:
        from app.invoice_service import generate_suborder_invoice
        from app.consumers.notification_consumer import handle_invoice_generated
        for so in missing_invoices:
            await generate_suborder_invoice(session=db, sub_order_id=so["sub_order_id"])
        await db.commit()
        await handle_invoice_generated({"order_id": str(oid)})
        # Re-fetch updated sub-orders and order status
        so_res = await db.execute(
            text("""
                SELECT so.id as sub_order_id, so.order_id, so.seller_id, so.city as package_city,
                       so.subtotal, so.tax, so.status as sub_order_status, so.created_at as so_created_at,
                       s.name as seller_name, s.seller_code, s.state as seller_state, s.gstin, s.address as seller_address,
                       i.id as invoice_id, i.invoice_no, i.taxable_value, i.cgst, i.sgst, i.igst, i.total as invoice_total, i.issued_at,
                       sh.id as shipment_id, sh.tracking_number, sh.status as shipment_status
                FROM sub_orders so
                JOIN sellers s ON s.id = so.seller_id
                LEFT JOIN invoices i ON i.sub_order_id = so.id
                LEFT JOIN shipments sh ON sh.sub_order_id = so.id
                WHERE so.order_id = :oid
                ORDER BY so.created_at ASC
            """),
            {"oid": oid},
        )
        sub_orders_rows = so_res.mappings().all()
        ord_res_updated = await db.execute(
            text("""
                SELECT id, customer_id, city, status, total_inr, grand_total,
                       invoices_expected, invoices_ready, created_at
                FROM orders
                WHERE id = :oid
            """),
            {"oid": oid},
        )
        order = ord_res_updated.mappings().first()

    # Fetch all items for this order
    items_res = await db.execute(
        text("""
            SELECT oi.id, oi.sub_order_id, oi.offer_id, oi.product_id, oi.quantity,
                   oi.unit_price_inr, p.name as product_name, p.sku
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = :oid
        """),
        {"oid": oid},
    )
    items = items_res.mappings().all()

    items_by_so: Dict[uuid.UUID, list] = {}
    for i in items:
        if i["sub_order_id"]:
            items_by_so.setdefault(i["sub_order_id"], []).append(i)

    sub_orders_payload = []
    for so in sub_orders_rows:
        so_id = so["sub_order_id"]
        sub_orders_payload.append({
            "sub_order_id": str(so_id),
            "seller": {
                "id": str(so["seller_id"]),
                "name": so["seller_name"],
                "seller_code": so["seller_code"],
                "state": so["seller_state"],
                "gstin": so["gstin"],
                "address": so["seller_address"],
            },
            "city": so["package_city"],
            "subtotal": float(so["subtotal"]),
            "tax": float(so["tax"]),
            "status": so["sub_order_status"],
            "invoice": {
                "id": str(so["invoice_id"]) if so["invoice_id"] else None,
                "invoice_no": so["invoice_no"],
                "taxable_value": float(so["taxable_value"]) if so["taxable_value"] is not None else None,
                "cgst": float(so["cgst"]) if so["cgst"] is not None else None,
                "sgst": float(so["sgst"]) if so["sgst"] is not None else None,
                "igst": float(so["igst"]) if so["igst"] is not None else None,
                "total": float(so["invoice_total"]) if so["invoice_total"] is not None else None,
                "issued_at": so["issued_at"].isoformat() if so["issued_at"] else None,
                "download_url": f"/invoices/{so['invoice_id']}/pdf" if so["invoice_id"] else None,
            } if so["invoice_no"] else None,
            "shipment": {
                "id": str(so["shipment_id"]) if so["shipment_id"] else None,
                "tracking_number": so["tracking_number"],
                "status": so["shipment_status"],
            } if so["shipment_id"] else None,
            "items": [
                {
                    "product_id": str(it["product_id"]),
                    "product_name": it["product_name"],
                    "sku": it["sku"],
                    "quantity": it["quantity"],
                    "unit_price_inr": float(it["unit_price_inr"]),
                }
                for it in items_by_so.get(so_id, [])
            ],
        })

    grand_tot = float(order["grand_total"] or order["total_inr"] or 0)
    invoices_exp = order["invoices_expected"] or len(sub_orders_payload)
    invoices_rdy = order["invoices_ready"] or sum(1 for so in sub_orders_payload if so.get("invoice"))

    return {
        "id": str(order["id"]),
        "customer_id": str(order["customer_id"]),
        "city": order["city"],
        "status": order["status"],
        "total_inr": grand_tot,
        "grand_total": grand_tot,
        "invoices_expected": invoices_exp,
        "invoices_ready": invoices_rdy,
        "all_invoices_ready": invoices_rdy >= invoices_exp,
        "invoices_download_url": f"/orders/{oid}/invoices.pdf" if invoices_rdy >= invoices_exp else None,
        "created_at": order["created_at"].isoformat() if order["created_at"] else None,
        "sub_orders": sub_orders_payload,
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


@router.get("/orders/{order_id}/summary")
async def get_order_summary_endpoint(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return consolidated order summary grouped by seller with single grand total."""
    order = await get_order_endpoint(order_id=order_id, db=db)
    return {
        "order_id": order["id"],
        "created_at": order["created_at"],
        "city": order["city"],
        "grand_total": order["grand_total"],
        "packages_count": len(order["sub_orders"]),
        "invoices_status": f"{order['invoices_ready']}/{order['invoices_expected']} Ready",
        "all_invoices_ready": order["all_invoices_ready"],
        "packages": [
            {
                "package_no": idx,
                "seller_name": so["seller"]["name"],
                "seller_gstin": so["seller"]["gstin"],
                "invoice_no": so["invoice"]["invoice_no"] if so.get("invoice") else "Pending",
                "tracking_number": so["shipment"]["tracking_number"] if so.get("shipment") else "Pending",
                "subtotal": so["subtotal"],
                "items_count": len(so["items"]),
                "items": so["items"],
            }
            for idx, so in enumerate(order["sub_orders"], 1)
        ],
    }


@router.get("/invoices/{invoice_id}/pdf")
async def download_single_invoice_pdf(
    invoice_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download individual GST Tax Invoice PDF for a seller sub-order."""
    try:
        inv_uuid = uuid.UUID(invoice_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid invoice UUID")

    res = await db.execute(
        text("""
            SELECT i.id, i.invoice_no, i.sub_order_id, i.taxable_value, i.cgst, i.sgst, i.igst,
                   i.total, i.issued_at,
                   s.name as seller_name, s.seller_code, s.state as seller_state, s.gstin, s.address as seller_address,
                   so.order_id, so.city as delivery_city,
                   o.customer_id,
                   c.name as customer_name, c.phone as customer_phone,
                   sh.tracking_number
            FROM invoices i
            JOIN sellers s ON s.id = i.seller_id
            JOIN sub_orders so ON so.id = i.sub_order_id
            JOIN orders o ON o.id = so.order_id
            LEFT JOIN customers c ON c.id = o.customer_id
            LEFT JOIN shipments sh ON sh.sub_order_id = so.id
            WHERE i.id = :iid OR so.id = :iid
        """),
        {"iid": inv_uuid},
    )
    inv = res.mappings().first()
    if not inv:
        # Check if iid is a sub_order that needs invoice generation
        so_check = await db.execute(text("SELECT id FROM sub_orders WHERE id = :iid"), {"iid": inv_uuid})
        if so_check.scalar():
            from app.invoice_service import generate_suborder_invoice
            await generate_suborder_invoice(session=db, sub_order_id=inv_uuid)
            await db.commit()
            return await download_single_invoice_pdf(invoice_id=invoice_id, db=db)
        raise HTTPException(status_code=404, detail="Tax Invoice not found")

    # Fetch line items for this sub-order
    items_res = await db.execute(
        text("""
            SELECT oi.quantity, oi.unit_price_inr, p.name as product_name, p.sku
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.sub_order_id = :soid
        """),
        {"soid": inv["sub_order_id"]},
    )
    items = items_res.mappings().all()

    inv_dict = {
        "invoice_no": inv["invoice_no"],
        "issued_at": inv["issued_at"],
        "order_id": str(inv["order_id"]),
        "sub_order_id": str(inv["sub_order_id"]),
        "delivery_city": inv["delivery_city"],
        "delivery_state": inv["seller_state"],
        "tracking_number": inv["tracking_number"] or "TRK-ASSIGNED",
        "taxable_value": inv["taxable_value"],
        "cgst": inv["cgst"],
        "sgst": inv["sgst"],
        "igst": inv["igst"],
        "total": inv["total"],
        "seller": {
            "name": inv["seller_name"],
            "seller_code": inv["seller_code"],
            "state": inv["seller_state"],
            "gstin": inv["gstin"],
            "address": inv["seller_address"],
        },
        "customer": {
            "name": inv["customer_name"] or "Priya Sharma",
            "phone": inv["customer_phone"] or "+91-9876543210",
        },
        "items": [dict(it) for it in items],
    }

    pdf_bytes = generate_single_invoice_pdf(inv_dict)
    filename = f"{inv['invoice_no'].replace('/', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/orders/{order_id}/invoices.pdf")
async def download_all_order_invoices_pdf(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download consolidated multi-page PDF (Order Summary + All Seller Tax Invoices).
    Returns 409 Conflict if invoices are still being generated.
    """
    order = await get_order_endpoint(order_id=order_id, db=db)

    # If any invoices are still pending, fulfill them on-the-fly immediately!
    if not order["all_invoices_ready"]:
        from app.invoice_service import generate_suborder_invoice
        from app.consumers.notification_consumer import handle_invoice_generated
        for so in order["sub_orders"]:
            if not so.get("invoice"):
                await generate_suborder_invoice(session=db, sub_order_id=so["sub_order_id"])
        await db.commit()
        await handle_invoice_generated({"order_id": order_id})
        order = await get_order_endpoint(order_id=order_id, db=db)

    # Fetch customer contact details
    cust_res = await db.execute(
        text("SELECT name, phone, email FROM customers WHERE id = :cid"),
        {"cid": uuid.UUID(order["customer_id"])},
    )
    cust_row = cust_res.mappings().first()
    cust_dict = dict(cust_row) if cust_row else {"name": "Priya Sharma", "phone": "+91-9876543210"}

    order_summary_data = {
        "order_id": order["id"],
        "created_at": order["created_at"],
        "city": order["city"],
        "grand_total": order["grand_total"],
        "customer": cust_dict,
        "sub_orders": order["sub_orders"],
    }

    # 1. Generate Order Summary Sheet
    summary_pdf_bytes = generate_order_summary_pdf(order_summary_data)

    # 2. Generate each seller's Tax Invoice PDF
    invoice_pdfs: List[bytes] = []
    for so in order["sub_orders"]:
        inv = so.get("invoice")
        if not inv:
            continue
        inv_dict = {
            "invoice_no": inv["invoice_no"],
            "issued_at": inv["issued_at"],
            "order_id": order["id"],
            "sub_order_id": so["sub_order_id"],
            "delivery_city": order["city"],
            "delivery_state": so["seller"]["state"],
            "tracking_number": so["shipment"]["tracking_number"] if so.get("shipment") else "TRK-ASSIGNED",
            "taxable_value": inv["taxable_value"],
            "cgst": inv["cgst"],
            "sgst": inv["sgst"],
            "igst": inv["igst"],
            "total": inv["total"],
            "seller": so["seller"],
            "customer": cust_dict,
            "items": so["items"],
        }
        invoice_pdfs.append(generate_single_invoice_pdf(inv_dict))

    # 3. Merge Summary + All Invoices into 1 multi-page PDF
    merged_pdf = merge_order_invoices_pdf(summary_pdf_bytes, invoice_pdfs)

    filename = f"order_{order['id'][:8]}_tax_invoices.pdf"
    return Response(
        content=merged_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



@router.post("/dev/stress-last-unit")
async def stress_last_unit_endpoint(
    req: StressTestRequestSchema = StressTestRequestSchema(),
) -> Dict[str, Any]:
    """Fires N concurrent checkout requests for exactly 1 remaining unit.
    Proves that two buyers can NEVER both get the last unit under race conditions.
    """
    target_city = req.city
    target_product_id = req.product_id

    try:
        # 1. If not specified, select a catalogue product to test concurrency on
        async with async_session_factory() as session:
            if not target_product_id:
                res = await session.execute(
                    text("SELECT id FROM products WHERE sku = 'MOB-0004'")
                )
                row = res.scalar_one_or_none()
                if not row:
                    res = await session.execute(text("SELECT id FROM products ORDER BY id ASC LIMIT 1"))
                    row = res.scalar_one_or_none()
                if not row:
                    raise HTTPException(status_code=404, detail="No products in catalogue to run stress test on.")
                target_product_id = str(row)

            # Reset stock to exactly 1 unit for the test
            # Reset store_stock to 1 unit in target city, 0 elsewhere
            await session.execute(
                text("UPDATE store_stock SET qty = 0, updated_at = NOW() WHERE product_id = :pid"),
                {"pid": target_product_id},
            )
            await session.execute(
                text("""
                    INSERT INTO store_stock (product_id, city, qty, updated_at)
                    VALUES (:pid, :city, 1, NOW())
                    ON CONFLICT (product_id, city) DO UPDATE SET qty = 1, updated_at = NOW()
                """),
                {"pid": target_product_id, "city": target_city},
            )
            # Ensure exactly 1 unit exists across seller_offers across ALL cities
            await session.execute(
                text("UPDATE seller_offers SET qty = 0, updated_at = NOW() WHERE product_id = :pid"),
                {"pid": target_product_id},
            )
            best_offer_res = await session.execute(
                text("SELECT id FROM seller_offers WHERE product_id = :pid AND city = :city LIMIT 1"),
                {"pid": target_product_id, "city": target_city},
            )
            best_offer_id = best_offer_res.scalar()
            if best_offer_id:
                await session.execute(
                    text("UPDATE seller_offers SET qty = 1, updated_at = NOW() WHERE id = :id"),
                    {"id": best_offer_id},
                )
            else:
                s_res = await session.execute(text("SELECT id FROM sellers LIMIT 1"))
                s_id = s_res.scalar()
                p_res = await session.execute(text("SELECT price_inr FROM products WHERE id = :pid"), {"pid": target_product_id})
                price = p_res.scalar() or 999.00
                await session.execute(
                    text("""
                        INSERT INTO seller_offers (id, product_id, seller_id, city, price_inr, qty, created_at, updated_at)
                        VALUES (gen_random_uuid(), :pid, :sid, :city, :price, 1, NOW(), NOW())
                    """),
                    {"pid": target_product_id, "sid": s_id, "city": target_city, "price": price},
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
                text("SELECT COALESCE(SUM(qty), 0) FROM seller_offers WHERE product_id = :pid AND city = :city"),
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stress test failed: {str(e)}")

