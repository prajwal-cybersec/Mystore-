import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session_factory
from sqlalchemy import text

# TryOn product configurations mapping
TRYON_BACKFILL_DATA = {
    # 1. Jockey Pink T-Shirt
    "FAS-0002": {
        "tryon_supported": True,
        "tryon_type": "tshirt",
        "tryon_asset": "/static/tryon/FAS-0002.png",
        "tryon_config": {
            "scale": 1.0,
            "scaleX": 1.4,
            "scaleY": 1.25,
            "offsetX": 0.0,
            "offsetY": -0.05,
            "offsetZ": 0.0,
            "rotation": 0.0,
            "flip": False,
            "fadeAngleDeg": 60.0
        }
    },
    # 2. Blue Squad Men Casual Black Shirt
    "FAS-0003": {
        "tryon_supported": True,
        "tryon_type": "shirt",
        "tryon_asset": "/static/tryon/FAS-0003.png",
        "tryon_config": {
            "scale": 1.0,
            "scaleX": 1.45,
            "scaleY": 1.35,
            "offsetX": 0.0,
            "offsetY": -0.04,
            "offsetZ": 0.0,
            "rotation": 0.0,
            "flip": False,
            "fadeAngleDeg": 60.0
        }
    },
    # 3. ellark Floral Print Straight Kurta
    "FAS-0007": {
        "tryon_supported": True,
        "tryon_type": "shirt",
        "tryon_asset": "/static/tryon/FAS-0007.png",
        "tryon_config": {
            "scale": 1.0,
            "scaleX": 1.45,
            "scaleY": 1.45,
            "offsetX": 0.0,
            "offsetY": -0.02,
            "offsetZ": 0.0,
            "rotation": 0.0,
            "flip": False,
            "fadeAngleDeg": 60.0
        }
    },
    # 4. Lakmé 9TO5 Primer + Matte Lip Color
    "BEA-0001": {
        "tryon_supported": True,
        "tryon_type": "lipstick",
        "tryon_asset": None,
        "tryon_config": {
            "opacity": 0.65,
            "blendMode": "multiply",
            "gloss": 0.35,
            "defaultColor": "#b74152",
            "colors": [
                {"name": "Rosy Sunday", "hex": "#b74152"},
                {"name": "Berry Base", "hex": "#7d2138"},
                {"name": "Nude Touch", "hex": "#b27a69"}
            ]
        }
    },
    # 5. Lakmé Showstopper Rouge Bloom Powder Blush
    "BEA-0002": {
        "tryon_supported": True,
        "tryon_type": "blush",
        "tryon_asset": None,
        "tryon_config": {
            "opacity": 0.45,
            "radiusMultiplier": 1.1,
            "blendMode": "source-over",
            "defaultColor": "#e07a8b",
            "colors": [
                {"name": "Pink Blossom", "hex": "#e07a8b"},
                {"name": "Peach Radiance", "hex": "#f4a282"},
                {"name": "Soft Coral", "hex": "#d96556"}
            ]
        }
    },
    # 6. boAt Rockerz 430 Gen 2 Bluetooth Headphones
    "ELE-0002": {
        "tryon_supported": True,
        "tryon_type": "headphones",
        "tryon_asset": "/static/tryon/ELE-0002.png",
        "tryon_config": {
            "scale": 1.05,
            "offsetX": 0.0,
            "offsetY": 0.02,
            "offsetZ": 0.0,
            "rotation": 0.0,
            "flip": False
        }
    }
}

async def backfill():
    async with async_session_factory() as session:
        # First reset all products to false
        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = false, 
                tryon_type = NULL, 
                tryon_asset = NULL, 
                tryon_config = '{}'::jsonb
        """))

        # Now apply mapped entries
        for sku, config in TRYON_BACKFILL_DATA.items():
            await session.execute(
                text("""
                    UPDATE products
                    SET tryon_supported = :supported,
                        tryon_type = :type,
                        tryon_asset = :asset,
                        tryon_config = :config
                    WHERE sku = :sku
                """),
                {
                    "sku": sku,
                    "supported": config["tryon_supported"],
                    "type": config["tryon_type"],
                    "asset": config["tryon_asset"],
                    "config": json.dumps(config["tryon_config"])
                }
            )
            print(f"Backfilled TryOn for {sku}: type={config['tryon_type']}, asset={config['tryon_asset']}")

        await session.commit()
        print("\nBackfill completed successfully!")

if __name__ == "__main__":
    asyncio.run(backfill())
