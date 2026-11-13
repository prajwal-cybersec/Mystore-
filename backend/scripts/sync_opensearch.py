"""Sync PostgreSQL products and store stock into OpenSearch index with embeddings."""

import asyncio
import json
import os
import structlog
import urllib3
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
import asyncpg
from opensearchpy.helpers import bulk

from app.opensearch_client import get_opensearch_client, ensure_products_index, INDEX_NAME
from app.embeddings import compute_batch_embeddings

urllib3.disable_warnings()
logger = structlog.stdlib.get_logger(__name__)

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


async def sync_all_products(batch_size: int = 50):
    """Read all products and stock from PostgreSQL and bulk-index to OpenSearch."""
    ensure_products_index(recreate=False)
    client = get_opensearch_client()

    pg_url = os.getenv("PG_URL").replace("postgres://", "postgresql://")
    conn = await asyncpg.connect(pg_url, ssl="require")

    print("Fetching products and stock from PostgreSQL...")
    products = await conn.fetch("""
        SELECT id, sku, name, brand, category, description, price_inr, image_url, attrs
        FROM products
        ORDER BY created_at ASC
    """)

    # Fetch all stock grouped by product
    stock_rows = await conn.fetch("""
        SELECT product_id, city, qty
        FROM store_stock
    """)
    await conn.close()

    stock_map = {}
    for r in stock_rows:
        pid = str(r["product_id"])
        if pid not in stock_map:
            stock_map[pid] = []
        stock_map[pid].append({
            "city": r["city"],
            "qty": r["qty"],
            "in_stock": r["qty"] > 0,
        })

    print(f"Total products fetched: {len(products)}. Preparing OpenSearch documents...")

    # Process in batches for embeddings and bulk insert
    total_indexed = 0
    docs_to_index = []

    for i in range(0, len(products), batch_size):
        chunk = products[i:i + batch_size]
        texts = [f"{p['brand']} {p['name']} {p['category']} {p['description']}" for p in chunk]
        
        # Compute embeddings for batch
        embeddings = compute_batch_embeddings(texts)

        for p, emb in zip(chunk, embeddings):
            pid = str(p["id"])
            p_stock = stock_map.get(pid, [])
            total_qty = sum(item["qty"] for item in p_stock)
            
            attrs_data = p["attrs"]
            if isinstance(attrs_data, str):
                try:
                    attrs_data = json.loads(attrs_data)
                except Exception:
                    attrs_data = {}

            doc = {
                "_index": INDEX_NAME,
                "_id": pid,
                "_source": {
                    "id": pid,
                    "sku": p["sku"],
                    "name": p["name"],
                    "brand": p["brand"],
                    "category": p["category"],
                    "description": p["description"],
                    "price_inr": float(p["price_inr"]),
                    "image_url": p["image_url"],
                    "attrs": attrs_data or {},
                    "in_stock": total_qty > 0,
                    "total_stock": total_qty,
                    "city_stock": p_stock,
                    "embedding": emb,
                }
            }
            docs_to_index.append(doc)

        print(f"Computed embeddings for batch {i}..{i + len(chunk)}")

    print(f"Bulk indexing {len(docs_to_index)} documents into OpenSearch...")
    success, failed = bulk(client, docs_to_index, refresh=True)
    print(f"OpenSearch Sync Complete: {success} indexed successfully, {len(failed)} failed.")
    client.indices.refresh(index=INDEX_NAME)


if __name__ == "__main__":
    asyncio.run(sync_all_products())

