"""Update product images in DB and OpenSearch with category-relevant, distinct Unsplash images."""

import asyncio
from sqlalchemy import text
from app.database import async_session_factory
from app.opensearch_client import get_opensearch_client

# Curated sets of high-res, authentic Unsplash images per category & sub-item
IMAGE_POOLS = {
    "phone": [
        "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1580910051074-3eb694886505?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=600&auto=format&fit=crop&q=80",
    ],
    "earbuds": [
        "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1606220588913-b3aacb4d2f46?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1572536147248-ac59a8abfa4b?w=600&auto=format&fit=crop&q=80",
    ],
    "watch": [
        "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1524805444758-089113d48a6d?w=600&auto=format&fit=crop&q=80",
    ],
    "tv_laptop": [
        "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600&auto=format&fit=crop&q=80",
    ],
    "electronics_gen": [
        "https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1550009158-9ebf69173e03?w=600&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1609081219090-a6d8173087ec?w=600&auto=format&fit=crop&q=80",
    ],
    "grocery": [
        "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", # rice
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80", # bread/atta
        "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=600&auto=format&fit=crop&q=80", # spices
        "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=600&auto=format&fit=crop&q=80", # spices/pulses
        "https://images.unsplash.com/photo-1471193945509-9ad0617afabf?w=600&auto=format&fit=crop&q=80", # tea/coffee
        "https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?w=600&auto=format&fit=crop&q=80", # grains
        "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600&auto=format&fit=crop&q=80", # grocery basket
    ],
    "fashion": [
        "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop&q=80", # apparel
        "https://images.unsplash.com/photo-1618244972963-dbee1a7edc95?w=600&auto=format&fit=crop&q=80", # ethnic kurta
        "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=600&auto=format&fit=crop&q=80", # shoes
        "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=600&auto=format&fit=crop&q=80", # jeans
        "https://images.unsplash.com/photo-1617137984095-74e4e5e3613f?w=600&auto=format&fit=crop&q=80", # kurta/menswear
        "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=600&auto=format&fit=crop&q=80", # sneakers
        "https://images.unsplash.com/photo-1600185365926-3a2ce3cdb9eb?w=600&auto=format&fit=crop&q=80", # footwear
    ],
    "home": [
        "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=600&auto=format&fit=crop&q=80", # cookware
        "https://images.unsplash.com/photo-1584269600464-37b1b58a9fe7?w=600&auto=format&fit=crop&q=80", # kitchen
        "https://images.unsplash.com/photo-1610557892470-55d9e80c0bce?w=600&auto=format&fit=crop&q=80", # pan
        "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92?w=600&auto=format&fit=crop&q=80", # home decor
        "https://images.unsplash.com/photo-1616401784845-180882ba9ba8?w=600&auto=format&fit=crop&q=80", # storage
        "https://images.unsplash.com/photo-1584990347449-39908cf6903d?w=600&auto=format&fit=crop&q=80", # pressure cooker/pots
    ],
    "personal_care": [
        "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=600&auto=format&fit=crop&q=80", # cosmetics
        "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # skincare
        "https://images.unsplash.com/photo-1608248597359-2e11894a864a?w=600&auto=format&fit=crop&q=80", # shampoo bottle
        "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?w=600&auto=format&fit=crop&q=80", # lotions
        "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=600&auto=format&fit=crop&q=80", # soaps/care
    ]
}

def pick_image(product_name: str, category: str, idx: int) -> str:
    name_l = product_name.lower()
    if category == "electronics":
        if any(w in name_l for w in ["phone", "galaxy s", "galaxy m", "galaxy a", "iphone", "pixel", "redmi", "nord", "realme"]):
            pool = IMAGE_POOLS["phone"]
        elif any(w in name_l for w in ["buds", "earphone", "headphone", "audio", "airpods", "speaker"]):
            pool = IMAGE_POOLS["earbuds"]
        elif any(w in name_l for w in ["watch", "band"]):
            pool = IMAGE_POOLS["watch"]
        elif any(w in name_l for w in ["tv", "pad", "tab", "laptop"]):
            pool = IMAGE_POOLS["tv_laptop"]
        else:
            pool = IMAGE_POOLS["electronics_gen"]
    elif category == "fashion":
        pool = IMAGE_POOLS["fashion"]
    elif category == "grocery":
        pool = IMAGE_POOLS["grocery"]
    elif category == "home":
        pool = IMAGE_POOLS["home"]
    elif category == "personal_care":
        pool = IMAGE_POOLS["personal_care"]
    else:
        pool = IMAGE_POOLS["electronics_gen"]
    
    # Consistent cycling based on hash & idx
    selected = pool[(hash(product_name) + idx) % len(pool)]
    # Add unique sig query param so browser cache treats each product uniquely
    return f"{selected}&sig={(abs(hash(product_name)) % 9999)}"

async def main():
    print("Updating product images in PostgreSQL and OpenSearch...")
    client = get_opensearch_client()
    
    async with async_session_factory() as s:
        res = await s.execute(text("SELECT id, name, category FROM products ORDER BY id"))
        products = res.fetchall()
        print(f"Loaded {len(products)} products from DB.")
        
        updates = []
        for i, p in enumerate(products):
            pid, name, cat = p
            img = pick_image(name, cat, i)
            updates.append({"id": pid, "img": img})
        
        # Batch update PostgreSQL
        for u in updates:
            await s.execute(
                text("UPDATE products SET image_url = :img WHERE id = :id"),
                {"img": u["img"], "id": u["id"]}
            )
        await s.commit()
        print("Updated all image_url rows in PostgreSQL.")
        
        # Batch update OpenSearch
        actions = []
        for u in updates:
            actions.append({"update": {"_index": "products", "_id": str(u["id"])}})
            actions.append({"doc": {"image_url": u["img"]}})
            
        # Push in chunks of 100
        for chunk_idx in range(0, len(actions), 200):
            chunk = actions[chunk_idx:chunk_idx+200]
            client.bulk(body=chunk)
        print("Updated OpenSearch products index with new image URLs.")

if __name__ == "__main__":
    asyncio.run(main())
