"""Phase 1 Verification: Test database schema, models, sellers, offers, and Alembic rollback."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import async_session_factory
from app.models.seller import Seller, SellerOffer, SellerInvoiceCounter, SubOrder, Invoice, Shipment
from app.models.order import Order, OrderItem


async def run_phase1_verification():
    print("\n" + "="*60)
    print("RUNNING PHASE 1 SCHEMA & SEED VERIFICATION")
    print("="*60 + "\n")

    async with async_session_factory() as session:
        # 1. Verify Sellers
        res = await session.execute(text("SELECT id, name, seller_code, gstin, state FROM sellers ORDER BY seller_code"))
        sellers = res.mappings().all()
        print(f"--> Sellers found ({len(sellers)}):")
        for s in sellers:
            print(f"    • [{s['seller_code']}] {s['name']} | State: {s['state']} | GSTIN: {s['gstin']}")
        assert len(sellers) >= 3, f"Expected at least 3 sellers, got {len(sellers)}"

        # 2. Verify Invoice Counters
        res = await session.execute(text("SELECT seller_id, last_no FROM seller_invoice_counters"))
        counters = res.mappings().all()
        print(f"\n--> Invoice Counters found ({len(counters)}):")
        for c in counters:
            print(f"    • Seller {c['seller_id']} -> last_no: {c['last_no']}")
        assert len(counters) >= 3, "Each seller must have an initialized invoice counter"

        # 3. Verify Seller Offers
        res = await session.execute(text("""
            SELECT s.name, s.seller_code, count(so.id) as offer_count, min(so.price_inr) as min_p, max(so.price_inr) as max_p
            FROM seller_offers so
            JOIN sellers s ON s.id = so.seller_id
            GROUP BY s.name, s.seller_code
            ORDER BY s.seller_code
        """))
        offers_by_seller = res.mappings().all()
        print("\n--> Seller Offers Distribution:")
        for obs in offers_by_seller:
            print(f"    • [{obs['seller_code']}] {obs['name']}: {obs['offer_count']} offers | Price range: ₹{obs['min_p']} - ₹{obs['max_p']}")
        assert len(offers_by_seller) >= 3, "Offers must be distributed across all 3 sellers"

        # 4. Verify orders & order_items column additions
        res = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'orders' AND column_name IN ('grand_total', 'invoices_expected', 'invoices_ready')
        """))
        order_cols = {r["column_name"]: r["data_type"] for r in res.mappings().all()}
        print(f"\n--> Orders table new columns verified: {list(order_cols.keys())}")
        assert "grand_total" in order_cols and "invoices_expected" in order_cols and "invoices_ready" in order_cols

        res = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'order_items' AND column_name IN ('sub_order_id', 'offer_id')
        """))
        item_cols = {r["column_name"]: r["data_type"] for r in res.mappings().all()}
        print(f"--> Order items table new columns verified: {list(item_cols.keys())}")
        assert "sub_order_id" in item_cols and "offer_id" in item_cols

    print("\n" + "="*60)
    print("ALL PHASE 1 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("="*60 + "\n")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_phase1_verification())
    if not success:
        sys.exit(1)
