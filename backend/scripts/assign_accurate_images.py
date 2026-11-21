"""Fine-grained accurate image mapper for all 310 products across Indian retail categories."""

import asyncio
from sqlalchemy import text
from app.database import async_session_factory
from app.opensearch_client import get_opensearch_client

# Authentic Unsplash high-resolution images categorized by specific item type
CATEGORY_IMAGE_MAP = {
    # --- GROCERY ---
    "atta": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80", # wheat flour / atta
    "dal": "https://images.unsplash.com/photo-1585994192701-f1a505c817ea?w=600&auto=format&fit=crop&q=80", # pulses, lentils, toor dal
    "toor": "https://images.unsplash.com/photo-1585994192701-f1a505c817ea?w=600&auto=format&fit=crop&q=80", # toor dal
    "moong": "https://images.unsplash.com/photo-1585994192701-f1a505c817ea?w=600&auto=format&fit=crop&q=80", # moong dal
    "rice": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", # basmati rice
    "basmati": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", # basmati rice
    "chawal": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", # rice
    "oil": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80", # cooking oil bottle
    "ghee": "https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=600&auto=format&fit=crop&q=80", # ghee / butter
    "butter": "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=600&auto=format&fit=crop&q=80", # butter pack
    "milk": "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=600&auto=format&fit=crop&q=80", # milk bottle / tetra
    "cheese": "https://images.unsplash.com/photo-1486297678162-eb2a19b0a32d?w=600&auto=format&fit=crop&q=80", # cheese block
    "bread": "https://images.unsplash.com/photo-1549931319-a545dcf3bc73?w=600&auto=format&fit=crop&q=80", # whole wheat bread loaf
    "biscuit": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80", # cookies / biscuits
    "cookie": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80", # cookies
    "chocolate": "https://images.unsplash.com/photo-1548907040-4baa42d10919?w=600&auto=format&fit=crop&q=80", # cadbury dairy milk chocolate
    "coffee": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=600&auto=format&fit=crop&q=80", # instant coffee
    "tea": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80", # tea leaves / chai
    "honey": "https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=600&auto=format&fit=crop&q=80", # pure honey jar
    "noodle": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=600&auto=format&fit=crop&q=80", # maggi / noodles
    "maggi": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=600&auto=format&fit=crop&q=80", # instant noodles
    "sauce": "https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=600&auto=format&fit=crop&q=80", # tomato ketchup / sauce
    "ketchup": "https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=600&auto=format&fit=crop&q=80", # tomato ketchup
    "masala": "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=600&auto=format&fit=crop&q=80", # spices / masala powder
    "spice": "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=600&auto=format&fit=crop&q=80", # spices
    "mirch": "https://images.unsplash.com/photo-1588252303782-cb80119abd6d?w=600&auto=format&fit=crop&q=80", # red chilli powder
    "haldi": "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=600&auto=format&fit=crop&q=80", # turmeric powder
    "salt": "https://images.unsplash.com/photo-1518110903415-8462050c0b44?w=600&auto=format&fit=crop&q=80", # table salt pouch
    "sugar": "https://images.unsplash.com/photo-1581441363689-1f3c3c414635?w=600&auto=format&fit=crop&q=80", # sugar
    "cereal": "https://images.unsplash.com/photo-1521483451569-e33803c0330c?w=600&auto=format&fit=crop&q=80", # corn flakes cereal
    "chocos": "https://images.unsplash.com/photo-1521483451569-e33803c0330c?w=600&auto=format&fit=crop&q=80", # cereal
    "namkeen": "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=600&auto=format&fit=crop&q=80", # haldiram namkeen / snacks
    "sweet": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=600&auto=format&fit=crop&q=80", # gulab jamun / sweets
    "jam": "https://images.unsplash.com/photo-1589733955941-5eeaf752f6dd?w=600&auto=format&fit=crop&q=80", # fruit jam jar
    "chyawanprash": "https://images.unsplash.com/photo-1624454002302-36b824d7bd0a?w=600&auto=format&fit=crop&q=80", # herbal paste / jar

    # --- ELECTRONICS ---
    "iphone": "https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600&auto=format&fit=crop&q=80", # Apple iPhone
    "galaxy s": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=600&auto=format&fit=crop&q=80", # Samsung Galaxy S Series
    "galaxy": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=600&auto=format&fit=crop&q=80", # Samsung phone
    "oneplus": "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=600&auto=format&fit=crop&q=80", # OnePlus smartphone
    "pixel": "https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=600&auto=format&fit=crop&q=80", # Google Pixel phone
    "realme": "https://images.unsplash.com/photo-1580910051074-3eb694886505?w=600&auto=format&fit=crop&q=80", # Realme smartphone
    "redmi": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80", # Xiaomi Redmi phone
    "phone": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80", # Smartphone generic
    "macbook": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&auto=format&fit=crop&q=80", # Apple MacBook
    "laptop": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&auto=format&fit=crop&q=80", # Windows Laptop (HP/Lenovo)
    "ideapad": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&auto=format&fit=crop&q=80", # Lenovo Laptop
    "pavilion": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&auto=format&fit=crop&q=80", # HP Laptop
    "ipad": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600&auto=format&fit=crop&q=80", # Apple iPad tablet
    "tab": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600&auto=format&fit=crop&q=80", # Tablet
    "pad": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600&auto=format&fit=crop&q=80", # Tablet
    "watch": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80", # Smartwatch
    "airpods": "https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=600&auto=format&fit=crop&q=80", # Apple AirPods Pro
    "earbuds": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80", # TWS Wireless Earbuds (boAt/Boult)
    "tws": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80", # TWS Earbuds
    "airdopes": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80", # boAt Airdopes
    "neckband": "https://images.unsplash.com/photo-1572536147248-ac59a8abfa4b?w=600&auto=format&fit=crop&q=80", # Bluetooth Neckband
    "headphone": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80", # Over-Ear Headphones (Sony/JBL)
    "headphones": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
    "wh-1000xm5": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80", # Sony WH-1000XM5 ANC headphones
    "noise cancelling": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
    "speaker": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=600&auto=format&fit=crop&q=80", # Portable Bluetooth Speaker (boAt Stone/JBL Flip)
    "soundbar": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=600&auto=format&fit=crop&q=80", # Soundbar / speaker
    "echo": "https://images.unsplash.com/photo-1543512214-318c7553f230?w=600&auto=format&fit=crop&q=80", # Amazon Echo Dot smart speaker
    "power bank": "https://images.unsplash.com/photo-1609081219090-a6d8173087ec?w=600&auto=format&fit=crop&q=80", # Power Bank
    "charger": "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?w=600&auto=format&fit=crop&q=80", # Wall Charger / adapter
    "mouse": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=600&auto=format&fit=crop&q=80", # Gaming Mouse (Logitech/EvoFox)
    "keyboard": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&auto=format&fit=crop&q=80", # Keyboard combo
    "printer": "https://images.unsplash.com/photo-1612815154858-60aa4c59eaa6?w=600&auto=format&fit=crop&q=80", # HP Laser Printer
    "tv": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=600&auto=format&fit=crop&q=80", # 4K Smart TV
    "ssd": "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=600&auto=format&fit=crop&q=80", # SSD Drive / storage
    "hdd": "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=600&auto=format&fit=crop&q=80", # HDD external drive
    "hard drive": "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=600&auto=format&fit=crop&q=80", # External HDD
    "portable hard": "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=600&auto=format&fit=crop&q=80", # WD/Seagate portable HDD
    "flash drive": "https://images.unsplash.com/photo-1587145820266-a5951ee6f620?w=600&auto=format&fit=crop&q=80", # USB Flash Drive
    "usb": "https://images.unsplash.com/photo-1587145820266-a5951ee6f620?w=600&auto=format&fit=crop&q=80", # USB drive/dongle
    "pendrive": "https://images.unsplash.com/photo-1587145820266-a5951ee6f620?w=600&auto=format&fit=crop&q=80", # Pen drive
    "dual drive": "https://images.unsplash.com/photo-1587145820266-a5951ee6f620?w=600&auto=format&fit=crop&q=80", # SanDisk Dual Drive
    "smart band": "https://images.unsplash.com/photo-1575311373937-040b8e1fd5b6?w=600&auto=format&fit=crop&q=80", # Xiaomi Smart Band / fitness tracker
    "smartwatch": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80", # Smartwatch
    "fire-boltt": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80", # Fire-Boltt smartwatch
    "noise two": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80", # Noise Two headphones (correct - over-ear)
    "noise pro": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80", # Noise Pro headphones
    "basshead": "https://images.unsplash.com/photo-1572536147248-ac59a8abfa4b?w=600&auto=format&fit=crop&q=80", # boAt Bassheads wired earphones
    "wired": "https://images.unsplash.com/photo-1572536147248-ac59a8abfa4b?w=600&auto=format&fit=crop&q=80", # Wired earphones/headphones
    "in-ear": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80", # In-ear earphones
    "router": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&auto=format&fit=crop&q=80", # Wi-Fi Router
    "wi-fi router": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&auto=format&fit=crop&q=80", # WiFi Router
    "multimedia speaker": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=600&auto=format&fit=crop&q=80", # Multimedia speakers
    "zebronics": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=600&auto=format&fit=crop&q=80", # Zebronics speakers/peripherals
    "xiaomi 14": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80", # Xiaomi 14 phone

    # --- FASHION ---
    "kurta": "https://images.unsplash.com/photo-1618244972963-dbee1a7edc95?w=600&auto=format&fit=crop&q=80", # Indian ethnic Kurta
    "anarkali": "https://images.unsplash.com/photo-1618244972963-dbee1a7edc95?w=600&auto=format&fit=crop&q=80", # Anarkali suit
    "saree": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600&auto=format&fit=crop&q=80", # Indian Saree pure silk
    "lehanga": "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=600&auto=format&fit=crop&q=80", # Indian Bridal Lehanga
    "nehru": "https://images.unsplash.com/photo-1617137984095-74e4e5e3613f?w=600&auto=format&fit=crop&q=80", # Nehru / Modi Jacket
    "shirt": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=600&auto=format&fit=crop&q=80", # Men's Casual / Formal Shirt
    "t-shirt": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=600&auto=format&fit=crop&q=80", # Cotton T-Shirt
    "tee": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=600&auto=format&fit=crop&q=80", # Sports T-Shirt
    "jeans": "https://images.unsplash.com/photo-1542272604-780c96856592?w=600&auto=format&fit=crop&q=80", # Levi's Denim Jeans
    "trousers": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=600&auto=format&fit=crop&q=80", # Formal Trousers / Pants
    "palazzo": "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=600&auto=format&fit=crop&q=80", # Palazzo pants
    "sneakers": "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=600&auto=format&fit=crop&q=80", # Running sneakers (Nike/Puma/Campus)
    "shoes": "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=600&auto=format&fit=crop&q=80", # Shoes / sneakers
    "loafers": "https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=600&auto=format&fit=crop&q=80", # Men's Leather Loafers (Bata/Hush Puppies)
    "derby": "https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=600&auto=format&fit=crop&q=80", # Derby leather shoes
    "sandals": "https://images.unsplash.com/photo-1603808033192-082d6919d3e1?w=600&auto=format&fit=crop&q=80", # Women's comfort sandals (Bata)
    "clogs": "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=600&auto=format&fit=crop&q=80", # Crocs foam clogs
    "belt": "https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=600&auto=format&fit=crop&q=80", # Leather Belt
    "handbag": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=600&auto=format&fit=crop&q=80", # Women's Handbag / Tote (Caprese/Lavie)
    "tote": "https://images.unsplash.com/photo-1597484661643-2f5fef640dd1?w=600&auto=format&fit=crop&q=80", # Jute Tote bag
    "backpack": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&auto=format&fit=crop&q=80", # Backpack
    "suitcase": "https://images.unsplash.com/photo-1565026057447-bc90a3dceb87?w=600&auto=format&fit=crop&q=80", # Luggage trolley suitcase
    "trolley": "https://images.unsplash.com/photo-1565026057447-bc90a3dceb87?w=600&auto=format&fit=crop&q=80", # Cabin luggage
    "luggage": "https://images.unsplash.com/photo-1565026057447-bc90a3dceb87?w=600&auto=format&fit=crop&q=80", # Luggage set
    "sunglasses": "https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=600&auto=format&fit=crop&q=80", # Fastrack Sunglasses
    "eyeglasses": "https://images.unsplash.com/photo-1591076482161-42ce6da69f67?w=600&auto=format&fit=crop&q=80", # Lenskart Eyeglasses
    "bangles": "https://images.unsplash.com/photo-1611591475879-1143a2f8b5a0?w=600&auto=format&fit=crop&q=80", # Traditional Bangles / Jewelry
    "briefs": "https://images.unsplash.com/photo-1582533561751-ef6f6ab93a2e?w=600&auto=format&fit=crop&q=80", # Jockey underwear
    "leggings": "https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=600&auto=format&fit=crop&q=80", # Gym leggings
    "suit": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600&auto=format&fit=crop&q=80", # Peter England formal suit

    # --- HOME & KITCHEN ---
    "cooker": "https://images.unsplash.com/photo-1584990347449-39908cf6903d?w=600&auto=format&fit=crop&q=80", # Pressure Cooker (Hawkins/Prestige)
    "kadhai": "https://images.unsplash.com/photo-1584990347449-39908cf6903d?w=600&auto=format&fit=crop&q=80", # Deep Kadhai / wok
    "pan": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=600&auto=format&fit=crop&q=80", # Frying Pan / Tea Pan
    "tawa": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=600&auto=format&fit=crop&q=80", # Dosa Tawa
    "grinder": "https://images.unsplash.com/photo-1574269909862-7e1d70bb8078?w=600&auto=format&fit=crop&q=80", # Mixer Grinder (Prestige/Bajaj)
    "mixer": "https://images.unsplash.com/photo-1574269909862-7e1d70bb8078?w=600&auto=format&fit=crop&q=80", # Mixer Grinder
    "blender": "https://images.unsplash.com/photo-1570222094114-d054a817e56b?w=600&auto=format&fit=crop&q=80", # Hand Blender
    "kettle": "https://images.unsplash.com/photo-1544233726-9f1d2b27be8b?w=600&auto=format&fit=crop&q=80", # Electric Kettle
    "iron": "https://images.unsplash.com/photo-1517677208171-0bc6725a3e60?w=600&auto=format&fit=crop&q=80", # Steam / Dry Iron (Philips/Bajaj)
    "purifier": "https://images.unsplash.com/photo-1527416876370-fb74d128c3dc?w=600&auto=format&fit=crop&q=80", # Water Purifier (Kent/Aquaguard)
    "aquaguard": "https://images.unsplash.com/photo-1527416876370-fb74d128c3dc?w=600&auto=format&fit=crop&q=80", # Water Purifier
    "geyser": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=600&auto=format&fit=crop&q=80", # Water Heater Geyser
    "heater": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=600&auto=format&fit=crop&q=80", # Water Heater
    "microwave": "https://images.unsplash.com/photo-1585659722983-3a675dabf23d?w=600&auto=format&fit=crop&q=80", # Microwave Oven
    "oven": "https://images.unsplash.com/photo-1585659722983-3a675dabf23d?w=600&auto=format&fit=crop&q=80", # Oven
    "fryer": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=600&auto=format&fit=crop&q=80", # Philips Air Fryer
    "cooktop": "https://images.unsplash.com/photo-1584990347449-39908cf6903d?w=600&auto=format&fit=crop&q=80", # Induction Cooktop
    "stove": "https://images.unsplash.com/photo-1584990347449-39908cf6903d?w=600&auto=format&fit=crop&q=80", # Gas Stove
    "vacuum": "https://images.unsplash.com/photo-1558317374-067fb5f30001?w=600&auto=format&fit=crop&q=80", # Vacuum Cleaner
    "mop": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=600&auto=format&fit=crop&q=80", # Floor Spin Mop (Spotzero/Milton)
    "bottle": "https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=600&auto=format&fit=crop&q=80", # Milton Stainless Steel Water Bottle
    "lunch box": "https://images.unsplash.com/photo-1594610156994-b7782ef0c0d8?w=600&auto=format&fit=crop&q=80", # Milton Lunch Box tiffin
    "container": "https://images.unsplash.com/photo-1584269600464-37b1b58a9fe7?w=600&auto=format&fit=crop&q=80", # Airtight Kitchen Container set
    "dinner set": "https://images.unsplash.com/photo-1614707267537-b85aaf00c4b7?w=600&auto=format&fit=crop&q=80", # Cello Opalware Dinner Set plates
    "bedsheet": "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=600&auto=format&fit=crop&q=80", # Double Bedsheet with Pillows
    "quilt": "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=600&auto=format&fit=crop&q=80", # Quilt Comforter
    "towel": "https://images.unsplash.com/photo-1616627547584-bf28cee262db?w=600&auto=format&fit=crop&q=80", # Cotton Bath Towels (Bombay Dyeing/Spaces)
    "bath mat": "https://images.unsplash.com/photo-1616627547584-bf28cee262db?w=600&auto=format&fit=crop&q=80", # Microfiber Bath Mat
    "mattress": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=600&auto=format&fit=crop&q=80", # Memory Foam Mattress (Wakefit/SleepyCat)
    "pillow": "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=600&auto=format&fit=crop&q=80", # Sleeping Pillows
    "fan": "https://images.unsplash.com/photo-1618941716939-553df3c6c278?w=600&auto=format&fit=crop&q=80", # Pedestal / Ceiling Fan (Usha/Crompton)
    "cooler": "https://images.unsplash.com/photo-1618941716939-553df3c6c278?w=600&auto=format&fit=crop&q=80", # Air Cooler
    "table": "https://images.unsplash.com/photo-1615066390971-03e4e1c36ddf?w=600&auto=format&fit=crop&q=80", # Dining Table set

    # --- PERSONAL CARE ---
    "toothpaste": "https://images.unsplash.com/photo-1559591937-e129188d3e23?w=600&auto=format&fit=crop&q=80", # Toothpaste tube (Colgate/Sensodyne/Patanjali)
    "shampoo": "https://images.unsplash.com/photo-1535585209827-a15fcdbc4c2d?w=600&auto=format&fit=crop&q=80", # Hair Shampoo bottle (Head & Shoulders/Tresemme)
    "soap": "https://images.unsplash.com/photo-1607006314146-565406d15a51?w=600&auto=format&fit=crop&q=80", # Bathing Soap bar (Dove/Dettol/Lifebuoy)
    "lotion": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # Body Lotion / Moisturizer (Nivea/Vaseline)
    "moisturizer": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # Face cream / moisturizer
    "cream": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # Face cream
    "facewash": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # Himalaya Neem Face Wash
    "face wash": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80", # Face Wash
    "hair oil": "https://images.unsplash.com/photo-1608248597359-2e11894a864a?w=600&auto=format&fit=crop&q=80", # Parachute Coconut Hair Oil
    "sunscreen": "https://images.unsplash.com/photo-1598440947619-2c35fc9aa908?w=600&auto=format&fit=crop&q=80", # Sunscreen lotion
    "perfume": "https://images.unsplash.com/photo-1592945403244-b3fbafd7f539?w=600&auto=format&fit=crop&q=80", # Men's Deodorant / Perfume (Wild Stone/Park Avenue)
    "deodorant": "https://images.unsplash.com/photo-1592945403244-b3fbafd7f539?w=600&auto=format&fit=crop&q=80", # Body Spray Deodorant
    "razor": "https://images.unsplash.com/photo-1508380702597-707c1b00a38c?w=600&auto=format&fit=crop&q=80", # Gillette Shaving Razor
    "shaving": "https://images.unsplash.com/photo-1508380702597-707c1b00a38c?w=600&auto=format&fit=crop&q=80", # Shaving Foam / gel
    "antiseptic": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=600&auto=format&fit=crop&q=80", # Dettol Liquid Antiseptic
}

# Fallbacks per high-level category
CATEGORY_FALLBACKS = {
    "grocery": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600&auto=format&fit=crop&q=80",
    "electronics": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
    "fashion": "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop&q=80",
    "home": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=600&auto=format&fit=crop&q=80",
    "personal_care": "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=600&auto=format&fit=crop&q=80",
}

import re

# Sort keys by length descending to match specific multi-word phrases first
SORTED_IMAGE_KEYS = sorted(CATEGORY_IMAGE_MAP.keys(), key=len, reverse=True)

def match_product_image(name: str, category: str) -> str:
    name_lower = name.lower()
    
    # Accurate whole-word and phrase matching
    for keyword in SORTED_IMAGE_KEYS:
        # Use regex word boundary so 'tee' does not match 'steel', 'atta' does not match 'dupatta', 'jam' does not match 'pajama'
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, name_lower):
            return CATEGORY_IMAGE_MAP[keyword]
            
    # Fallback to general category image
    return CATEGORY_FALLBACKS.get(category, CATEGORY_FALLBACKS["grocery"])

async def main():
    print("Assigning authentic item-specific images to all 310 products...")
    client = get_opensearch_client()
    
    async with async_session_factory() as s:
        res = await s.execute(text("SELECT id, name, category FROM products ORDER BY id"))
        products = res.fetchall()
        print(f"Loaded {len(products)} products from PostgreSQL.")
        
        updates = []
        for p in products:
            pid, name, cat = p
            img = match_product_image(name, cat)
            updates.append({"id": pid, "img": img, "name": name})
            
        # Update PostgreSQL
        for u in updates:
            await s.execute(
                text("UPDATE products SET image_url = :img WHERE id = :id"),
                {"img": u["img"], "id": u["id"]}
            )
        await s.commit()
        print("Updated all 310 image URLs in PostgreSQL database.")
        
        # Update OpenSearch
        actions = []
        for u in updates:
            actions.append({"update": {"_index": "products", "_id": str(u["id"])}})
            actions.append({"doc": {"image_url": u["img"]}})
            
        for chunk_idx in range(0, len(actions), 200):
            chunk = actions[chunk_idx:chunk_idx+200]
            client.bulk(body=chunk)
        print("Updated OpenSearch products index with accurate matching images.")

if __name__ == "__main__":
    asyncio.run(main())
