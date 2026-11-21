import asyncio
import json
from app.database import async_session_factory
from sqlalchemy import text

async def update_all_sections():
    async with async_session_factory() as session:
        cfg = json.dumps({
            'scale': 1.0,
            'scaleX': 1.0,
            'scaleY': 1.0,
            'offsetX': 0.0,
            'offsetY': 0.0,
            'rotation': 0.0,
            'opacity': 1.0,
            'flip': False
        })
        
        # 1. Mobiles: iPhone 17 (MOB-0002)
        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = true, 
                tryon_type = 'handheld_device', 
                tryon_asset = '/static/tryon/MOB-0002.png', 
                tryon_config = :cfg 
            WHERE sku = 'MOB-0002'
        """), {'cfg': cfg})

        # 2. Appliances: Foxsky 43-inch TV (ELE-0001)
        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = true, 
                tryon_type = 'room_ar', 
                tryon_asset = '/static/tryon/ELE-0001.png', 
                tryon_config = :cfg 
            WHERE sku = 'ELE-0001'
        """), {'cfg': cfg})

        # 3. Ensure Fashion black shirt (FAS-0003) and pink tshirt (FAS-0002) are calibrated
        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = true, 
                tryon_type = 'shirt', 
                tryon_asset = '/static/tryon/FAS-0003.png', 
                tryon_config = :cfg 
            WHERE sku = 'FAS-0003'
        """), {'cfg': cfg})

        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = true, 
                tryon_type = 'tshirt', 
                tryon_asset = '/static/tryon/FAS-0002.png', 
                tryon_config = :cfg 
            WHERE sku = 'FAS-0002'
        """), {'cfg': cfg})

        # 4. Electronics headphones (ELE-0002)
        await session.execute(text("""
            UPDATE products 
            SET tryon_supported = true, 
                tryon_type = 'headphones', 
                tryon_asset = '/static/tryon/ELE-0002.png', 
                tryon_config = :cfg 
            WHERE sku = 'ELE-0002'
        """), {'cfg': cfg})

        await session.commit()
        print("Successfully enabled Try-On with 3D capabilities across ALL sections (Fashion, Electronics, Beauty, Mobiles, Appliances)!")

if __name__ == '__main__':
    asyncio.run(update_all_sections())
