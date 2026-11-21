"""Idempotent seed script: inserts 300+ realistic Indian retail products across 5 cities,
along with store stock and a demo customer.
"""

import asyncio
import json
import os
import random
import uuid
from decimal import Decimal
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

CITIES = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai"]

ELECTRONICS_DATA = [
    # (name, brand, price, sku, attrs)
    ("Samsung Galaxy M14 5G (128GB)", "Samsung", 12999, "EL-SAM-001", {"color": "Smoky Teal", "storage": "128GB", "ram": "6GB"}),
    ("Samsung Galaxy S24 Ultra (256GB)", "Samsung", 129999, "EL-SAM-002", {"color": "Titanium Gray", "storage": "256GB", "ram": "12GB"}),
    ("Samsung Galaxy A55 5G (128GB)", "Samsung", 39999, "EL-SAM-003", {"color": "Awesome Iceblue", "storage": "128GB", "ram": "8GB"}),
    ("Samsung Galaxy Watch 6 Bluetooth (44mm)", "Samsung", 24999, "EL-SAM-004", {"color": "Graphite", "dial_size": "44mm"}),
    ("Samsung Galaxy Buds 2 Pro", "Samsung", 14999, "EL-SAM-005", {"color": "Bora Purple", "anc": True}),
    ("Samsung 43-inch Crystal 4K Vivid Pro TV", "Samsung", 28990, "EL-SAM-006", {"display_size": "43 inch", "resolution": "4K UHD"}),
    ("Samsung Galaxy Tab S9 FE (Wi-Fi 128GB)", "Samsung", 34999, "EL-SAM-007", {"screen": "10.9 inch", "storage": "128GB"}),
    ("OnePlus 12 (512GB)", "OnePlus", 69999, "EL-1PL-001", {"color": "Flowy Emerald", "storage": "512GB", "ram": "16GB"}),
    ("OnePlus Nord CE 4 (128GB)", "OnePlus", 24999, "EL-1PL-002", {"color": "Celadon Marble", "storage": "128GB", "ram": "8GB"}),
    ("OnePlus Nord Buds 3 Pro ANC", "OnePlus", 2799, "EL-1PL-003", {"color": "Starry Black", "battery": "44h"}),
    ("OnePlus Watch 2 Smartwatch", "OnePlus", 21999, "EL-1PL-004", {"battery": "100h", "os": "WearOS"}),
    ("OnePlus Pad 2 (256GB)", "OnePlus", 42999, "EL-1PL-005", {"screen": "11.6 inch", "chipset": "Snapdragon 8 Gen 3"}),
    ("Realme 12 Pro+ 5G (256GB)", "Realme", 29999, "EL-REL-001", {"color": "Submarine Blue", "camera": "64MP Periscope"}),
    ("Realme Narzo 70 Pro 5G (128GB)", "Realme", 18999, "EL-REL-002", {"color": "Glass Green", "ram": "8GB"}),
    ("Realme Buds Air 6 Wireless Earbuds", "Realme", 3299, "EL-REL-003", {"color": "Flame Silver", "anc": "50dB"}),
    ("Xiaomi Redmi Note 13 Pro 5G", "Xiaomi", 23999, "EL-XIA-001", {"camera": "200MP", "storage": "128GB"}),
    ("Xiaomi 14 Ultra (512GB)", "Xiaomi", 99999, "EL-XIA-002", {"camera": "Leica Quad", "storage": "512GB"}),
    ("Xiaomi Smart Band 8 Active", "Xiaomi", 1999, "EL-XIA-003", {"water_resistant": "5ATM", "battery": "14 days"}),
    ("Xiaomi Pad 6 (128GB, Wi-Fi)", "Xiaomi", 24999, "EL-XIA-004", {"screen": "11 inch 144Hz", "ram": "6GB"}),
    ("Apple iPhone 15 (128GB)", "Apple", 71999, "EL-APP-001", {"color": "Blue", "storage": "128GB"}),
    ("Apple iPhone 15 Pro Max (256GB)", "Apple", 151990, "EL-APP-002", {"color": "Natural Titanium", "storage": "256GB"}),
    ("Apple AirPods Pro (2nd Gen with USB-C)", "Apple", 22900, "EL-APP-003", {"anc": True, "connector": "USB-C"}),
    ("Apple Watch Series 9 GPS (45mm)", "Apple", 41999, "EL-APP-004", {"color": "Midnight", "case": "Aluminium"}),
    ("Apple iPad Air 11-inch M2 (128GB)", "Apple", 59900, "EL-APP-005", {"chip": "M2", "storage": "128GB"}),
    ("Apple MacBook Air M3 (13.6-inch, 256GB)", "Apple", 104990, "EL-APP-006", {"ram": "8GB", "ssd": "256GB"}),
    ("boAt Airdopes 141 Bluetooth TWS Earbuds", "boAt", 1299, "EL-BOA-001", {"battery": "42h", "playback": "Beast Mode"}),
    ("boAt Rockerz 255 Pro+ Neckband", "boAt", 1499, "EL-BOA-002", {"battery": "60h", "ip_rating": "IPX7"}),
    ("boAt Wave Call 2 Smartwatch", "boAt", 1399, "EL-BOA-003", {"display": "1.83 inch HD", "calling": True}),
    ("boAt Stone 350 10W Bluetooth Speaker", "boAt", 1499, "EL-BOA-004", {"power": "10W", "battery": "12h"}),
    ("boAt Nirvana Ion ANC Earbuds", "boAt", 2499, "EL-BOA-005", {"battery": "120h", "anc": "32dB"}),
    ("boAt Bassheads 100 Wired in-Ear Earphones", "boAt", 399, "EL-BOA-006", {"cable": "Hawk inspired", "mic": True}),
    ("JBL Flip 6 Portable Bluetooth Speaker", "JBL", 9999, "EL-JBL-001", {"waterproof": "IP67", "battery": "12h"}),
    ("JBL Tune 770NC Wireless Over-Ear ANC Headphones", "JBL", 5999, "EL-JBL-002", {"battery": "70h", "anc": True}),
    ("JBL Go 3 Eco Ultra-Portable Speaker", "JBL", 2999, "EL-JBL-003", {"battery": "5h", "waterproof": "IP67"}),
    ("JBL Wave Beam True Wireless Earbuds", "JBL", 3499, "EL-JBL-004", {"battery": "32h", "bass": "Deep Bass"}),
    ("JBL Cinema SB190 380W Dolby Atmos Soundbar", "JBL", 19999, "EL-JBL-005", {"audio": "Dolby Atmos", "subwoofer": "Wireless"}),
    ("Lenovo IdeaPad Slim 3 12th Gen Intel Core i3", "Lenovo", 34990, "EL-LEN-001", {"ram": "8GB", "ssd": "512GB", "screen": "15.6 inch"}),
    ("Lenovo LOQ 15 Gaming Laptop Intel i5 13th Gen", "Lenovo", 74990, "EL-LEN-002", {"gpu": "RTX 4050 6GB", "ram": "16GB"}),
    ("Lenovo ThinkPad E14 Gen 5 AMD Ryzen 5", "Lenovo", 52990, "EL-LEN-003", {"ram": "16GB", "ssd": "512GB"}),
    ("HP 15s 12th Gen Intel Core i5 Laptop", "HP", 51990, "EL-HP-001", {"ram": "16GB", "ssd": "512GB", "os": "Windows 11"}),
    ("HP Pavilion Gaming 15 Laptop AMD Ryzen 5", "HP", 64990, "EL-HP-002", {"gpu": "RTX 3050", "ram": "16GB"}),
    ("HP LaserJet Pro MFP Multi-Function Wireless Printer", "HP", 17499, "EL-HP-003", {"type": "Monochrome Laser", "wireless": True}),
    ("Sony WH-1000XM5 Wireless Industry Noise Cancelling", "Sony", 28990, "EL-SON-001", {"anc": "Dual Processor V1", "battery": "30h"}),
    ("Sony PlayStation 5 Slim Disc Edition", "Sony", 54990, "EL-SON-002", {"storage": "1TB SSD", "resolution": "4K 120Hz"}),
    ("Sony Bravia 55-inch 4K Google TV", "Sony", 57990, "EL-SON-003", {"display": "4K HDR", "audio": "Dolby Audio"}),
    ("Sony WF-C700N Truly Wireless Earbuds", "Sony", 7990, "EL-SON-004", {"anc": True, "battery": "15h"}),
    ("Noise ColorFit Pulse 2 Max Smartwatch", "Noise", 1499, "EL-NOI-001", {"display": "1.85 inch", "bt_calling": True}),
    ("Noise Buds VS104 Truly Wireless Earbuds", "Noise", 1099, "EL-NOI-002", {"playback": "45h", "driver": "13mm"}),
    ("Noise Diva Smartwatch for Women", "Noise", 2999, "EL-NOI-003", {"strap": "Mesh Metal", "display": "AMOLED"}),
    ("Portronics Ruffpad 8.5M Re-Writable LCD Pad", "Portronics", 299, "EL-POR-001", {"screen": "8.5 inch", "type": "Stylus Drawing"}),
    ("Portronics Power Plate 7 Power Strip Surge Protector", "Portronics", 899, "EL-POR-002", {"ports": "6 Sockets + 4 USB", "cord": "3m"}),
    ("Ambrane 20000mAh Power Bank 20W Fast Charging", "Ambrane", 1599, "EL-AMB-001", {"capacity": "20000mAh", "output": "20W PD"}),
    ("SanDisk 128GB Ultra Dual Drive Luxe USB Type-C", "SanDisk", 1199, "EL-SND-001", {"capacity": "128GB", "interface": "USB 3.1"}),
    ("Logitech MK215 Wireless Keyboard and Mouse Combo", "Logitech", 1395, "EL-LOG-001", {"wireless": "2.4GHz", "battery_life": "24 months"}),
    ("Logitech MX Master 3S Wireless Performance Mouse", "Logitech", 9495, "EL-LOG-002", {"sensor": "8K DPI", "quiet": True}),
    ("TP-Link Archer C6 AC1200 Dual Band Wi-Fi Router", "TP-Link", 2299, "EL-TPL-001", {"speed": "1200Mbps", "antennas": "4 External"}),
    ("Fire-Boltt Phoenix Pro Bluetooth Calling Smartwatch", "Fire-Boltt", 1499, "EL-FIR-001", {"display": "1.39 inch Round", "calling": True}),
    ("Zebronics Zeb-Warrior 2.0 Multimedia Speakers", "Zebronics", 699, "EL-ZEB-001", {"power": "10W RMS", "rgb": True}),
    ("Mi 33W SonicCharge 2.0 Fast Wall Charger", "Xiaomi", 999, "EL-XIA-005", {"power": "33W", "ports": "USB-A to Type-C"}),
    ("OnePlus SuperVOOC 80W Power Adapter", "OnePlus", 2499, "EL-1PL-006", {"power": "80W", "type": "Type-C"}),
    ("Realme Buds Wireless 3 in-Ear Neckband", "Realme", 1699, "EL-REL-004", {"driver": "13.6mm Bass", "anc": "30dB"}),
    ("boAt Storm Call 3 Smartwatch with Turn-by-Turn Nav", "boAt", 1799, "EL-BOA-007", {"navigation": True, "display": "1.83 inch"}),
    ("Boult Audio Z40 True Wireless Earbuds", "Boult", 1199, "EL-BOU-001", {"playback": "60h", "latency": "Zen ENC"}),
    ("Boult Audio Drift Pro AMOLED Smartwatch", "Boult", 1999, "EL-BOU-002", {"display": "1.43 inch AMOLED", "calling": True}),
    ("Noise Airwave Wireless Neckband Earphones", "Noise", 999, "EL-NOI-004", {"battery": "50h", "charging": "Instacharge"}),
    ("Zebronics Transformer Gaming Keyboard Mouse Combo", "Zebronics", 1299, "EL-ZEB-002", {"keys": "Braided Cable", "rgb": True}),
    ("EvoFox Shadow USB Wired Gaming Mouse 7200 DPI", "EvoFox", 549, "EL-EVO-001", {"dpi": "7200", "led": "RGB"}),
    ("Redragon Kumara K552 Mechanical Gaming Keyboard", "Redragon", 2699, "EL-RED-001", {"switches": "Blue Clicky", "backlit": "Rainbow LED"}),
    ("Crucial P3 1TB PCIe 3.0 3D NAND NVMe M.2 SSD", "Crucial", 5699, "EL-CRU-001", {"speed": "3500MB/s", "capacity": "1TB"}),
    ("Western Digital Elements 1.5TB Portable Hard Drive", "Western Digital", 5299, "EL-WDC-001", {"capacity": "1.5TB", "interface": "USB 3.0"}),
    ("Seagate One Touch 2TB External HDD with Password", "Seagate", 6499, "EL-SEA-001", {"capacity": "2TB", "security": "AES-256"}),
    ("Belkin 3-in-1 Wireless Charger with MagSafe 15W", "Belkin", 13999, "EL-BEL-001", {"magsafe": True, "power": "15W"}),
    ("Anker 737 Power Bank PowerCore 24K (140W)", "Anker", 11999, "EL-ANK-001", {"capacity": "24000mAh", "speed": "140W Two-Way"}),
    ("Amazon Fire TV Stick 4K with Alexa Voice Remote", "Amazon", 4499, "EL-AMZ-001", {"streaming": "4K Ultra HD", "remote": "Voice Remote"}),
    ("Amazon Echo Dot 5th Gen Smart Speaker with Alexa", "Amazon", 4449, "EL-AMZ-002", {"audio": "Deeper Bass", "smart_home": True}),
    ("Google Pixel 8a (128GB, Bay Blue)", "Google", 49999, "EL-GOO-001", {"ai": "Gemini Nano", "camera": "64MP + 13MP"}),
    ("Google Nest Mini 2nd Gen Smart Speaker", "Google", 3499, "EL-GOO-002", {"assistant": "Google Assistant", "voice": "Voice Match"}),
    ("Noise Two Wireless On-Ear Headphones with 50H", "Noise", 1699, "EL-NOI-005", {"battery": "50h", "bass": "Tru Bass"}),
    ("boAt Immortal 121 TWS Gaming Earbuds Low Latency", "boAt", 1499, "EL-BOA-008", {"latency": "40ms BEAST Mode", "rgb": True}),
    ("Ptron Bassbuds Duo in-Ear Earbuds", "Ptron", 799, "EL-PTR-001", {"playback": "32h", "type": "Type-C Fast Charge"}),
]

GROCERY_DATA = [
    ("Aashirvaad Superior MP Whole Wheat Atta 10kg", "Aashirvaad", 485, "GR-AAS-001", {"weight": "10kg", "organic": False, "grains": "Whole Wheat"}),
    ("Aashirvaad Select Sharbati Whole Wheat Atta 5kg", "Aashirvaad", 310, "GR-AAS-002", {"weight": "5kg", "origin": "Madhya Pradesh"}),
    ("Aashirvaad Svasti Pure Cow Ghee 1L Pouch", "Aashirvaad", 645, "GR-AAS-003", {"volume": "1L", "fat_content": "Pure Cow Milk Fat"}),
    ("Aashirvaad Salt 1kg Pouch", "Aashirvaad", 28, "GR-AAS-004", {"weight": "1kg", "iodized": True}),
    ("Fortune Sunlite Refined Sunflower Oil 1L Pouch", "Fortune", 125, "GR-FOR-001", {"volume": "1L", "vitamins": "A and D"}),
    ("Fortune Kachi Ghani Pure Mustard Oil 1L Bottle", "Fortune", 148, "GR-FOR-002", {"volume": "1L", "method": "Cold Pressed"}),
    ("Fortune Premium Kardi Oil 5L Jar", "Fortune", 850, "GR-FOR-003", {"volume": "5L", "heart_friendly": True}),
    ("Fortune Biryani Special Basmati Rice 5kg", "Fortune", 549, "GR-FOR-004", {"weight": "5kg", "grain_length": "Extra Long"}),
    ("Fortune Rozana Basmati Rice 5kg", "Fortune", 389, "GR-FOR-005", {"weight": "5kg", "grain_length": "Medium Long"}),
    ("Tata Sampann Unpolished Toor Dal / Arhar Dal 1kg", "Tata", 185, "GR-TAT-001", {"weight": "1kg", "unpolished": True}),
    ("Tata Sampann Unpolished Chana Dal 1kg", "Tata", 115, "GR-TAT-002", {"weight": "1kg", "unpolished": True}),
    ("Tata Sampann Unpolished Moong Dal Yellow Split 1kg", "Tata", 160, "GR-TAT-003", {"weight": "1kg", "unpolished": True}),
    ("Tata Salt Vacuum Evaporated Iodized Salt 1kg", "Tata", 27, "GR-TAT-004", {"weight": "1kg", "iodized": True}),
    ("Tata Tea Premium Desh Ki Chai 1kg Pouch", "Tata", 420, "GR-TAT-005", {"weight": "1kg", "blend": "Assam and Darjeeling"}),
    ("Tata Tea Gold Rich Taste & Irresistible Aroma 500g", "Tata", 295, "GR-TAT-006", {"weight": "500g", "leaves": "Long Leaves Blend"}),
    ("Tata Sampann Red Chilli Powder 500g", "Tata", 210, "GR-TAT-007", {"weight": "500g", "stemless": True}),
    ("Tata Sampann Turmeric / Haldi Powder 500g", "Tata", 165, "GR-TAT-008", {"weight": "500g", "curcumin": "3% Natural"}),
    ("MDH Deggi Mirch Powder 100g", "MDH", 88, "GR-MDH-001", {"weight": "100g", "type": "Kashmiri Red Pepper Blend"}),
    ("MDH Chana Masala Spice Mix 100g", "MDH", 82, "GR-MDH-002", {"weight": "100g", "spiciness": "Medium"}),
    ("MDH Kitchen King All-Purpose Spices 100g", "MDH", 86, "GR-MDH-003", {"weight": "100g", "usage": "Vegetable curries"}),
    ("MDH Garam Masala Powder 100g", "MDH", 98, "GR-MDH-004", {"weight": "100g", "aroma": "Rich and Fragrant"}),
    ("MDH Sambhar Masala 100g", "MDH", 78, "GR-MDH-005", {"weight": "100g", "cuisine": "South Indian"}),
    ("Everest Chaat Masala 100g Carton", "Everest", 68, "GR-EVE-001", {"weight": "100g", "flavor": "Tangy and Spicy"}),
    ("Everest Pav Bhaji Masala 100g", "Everest", 76, "GR-EVE-002", {"weight": "100g", "cuisine": "Mumbai Street Food"}),
    ("Everest Shahi Paneer Masala 100g", "Everest", 82, "GR-EVE-003", {"weight": "100g", "flavor": "Creamy Nutty"}),
    ("Everest Coriander / Dhania Powder 500g", "Everest", 145, "GR-EVE-004", {"weight": "500g", "quality": "Agmark Grade A"}),
    ("Amul Taaza Homogenised Toned Milk 1L Tetra", "Amul", 72, "GR-AMU-001", {"volume": "1L", "fat": "3.0%", "snf": "8.5%"}),
    ("Amul Pasteurized Salted Butter 500g Carton", "Amul", 275, "GR-AMU-002", {"weight": "500g", "salted": True}),
    ("Amul Processed Cheese Block 500g", "Amul", 290, "GR-AMU-003", {"weight": "500g", "protein": "High"}),
    ("Amul Pure Ghee 1L Tin", "Amul", 630, "GR-AMU-004", {"volume": "1L", "texture": "Granular Danedaar"}),
    ("Amul Mithai Mate Sweetened Condensed Milk 400g", "Amul", 135, "GR-AMU-005", {"weight": "400g", "usage": "Desserts and Sweets"}),
    ("Parle-G Original Gluco Biscuits 800g Family Pack", "Parle", 75, "GR-PAR-001", {"weight": "800g", "type": "Glucose Biscuit"}),
    ("Parle Hide & Seek Chocolate Chip Biscuits 350g", "Parle", 110, "GR-PAR-002", {"weight": "350g", "chocolate": "Rich Cocoa Chips"}),
    ("Parle Monaco Salted Crackers 400g Value Pack", "Parle", 65, "GR-PAR-003", {"weight": "400g", "flavor": "Classic Salted"}),
    ("Britannia Good Day Butter Cookies 600g Mega Pack", "Britannia", 130, "GR-BRI-001", {"weight": "600g", "butter": "Real Butter"}),
    ("Britannia Bourbon Chocolate Cream Biscuits 390g", "Britannia", 85, "GR-BRI-002", {"weight": "390g", "cream": "Rich Chocolate"}),
    ("Britannia Marie Gold Crisp Tea Time Biscuits 1kg", "Britannia", 145, "GR-BRI-003", {"weight": "1kg", "vitamins": "Essential Vitamins"}),
    ("Britannia 100% Whole Wheat Brown Bread 400g", "Britannia", 55, "GR-BRI-004", {"weight": "400g", "wheat": "100% Atta"}),
    ("Maggi 2-Minute Masala Instant Noodles 12-Pack (840g)", "Maggi", 168, "GR-MAG-001", {"weight": "840g", "pack": "12 Units", "flavor": "Authentic Masala"}),
    ("Maggi Hot & Sweet Chilli Tomato Sauce 1kg Bottle", "Maggi", 175, "GR-MAG-002", {"weight": "1kg", "flavor": "Tangy & Fiery"}),
    ("Maggi Magic Cubes Vegetarian Seasoning 10 Cubes", "Maggi", 55, "GR-MAG-003", {"cubes": 10, "type": "Veg Broth Enhancer"}),
    ("Haldiram's Nagpur Bhujia Sev Namkeen 1kg", "Haldirams", 260, "GR-HAL-001", {"weight": "1kg", "spiciness": "Mild Spicy", "moth": "Moth Flour"}),
    ("Haldiram's All in One Savory Namkeen Mixture 400g", "Haldirams", 125, "GR-HAL-002", {"weight": "400g", "ingredients": "Cornflakes, Cashews, Sev"}),
    ("Haldiram's Gulab Jamun Instant Sweet Tin 1kg", "Haldirams", 240, "GR-HAL-003", {"weight": "1kg", "servings": "16 Pieces"}),
    ("Haldiram's Soan Papdi Festive Ghee Sweet 500g", "Haldirams", 180, "GR-HAL-004", {"weight": "500g", "cardamom": True}),
    ("MTR Minute Masala Idli Breakfast Mix 500g", "MTR", 115, "GR-MTR-001", {"weight": "500g", "prep_time": "10 mins"}),
    ("MTR Crispy Dosa Ready Breakfast Mix 500g", "MTR", 120, "GR-MTR-002", {"weight": "500g", "yield": "12-14 Dosas"}),
    ("MTR Ready to Eat Paneer Butter Masala 300g", "MTR", 130, "GR-MTR-003", {"weight": "300g", "preservatives": False}),
    ("MTR Rasam Powder Authentic Traditional 200g", "MTR", 95, "GR-MTR-004", {"weight": "200g", "flavor": "Peppery Spicy"}),
    ("Nestle Everyday Dairy Whitener Milk Powder 1kg", "Nestle", 550, "GR-NES-001", {"weight": "1kg", "solubility": "Instant"}),
    ("Nescafe Classic Pure Instant Coffee 200g Glass Jar", "Nescafe", 620, "GR-NES-002", {"weight": "200g", "roast": "Medium-Dark"}),
    ("Bru Instant Coffee Chicory Mixture 200g Pouch", "Bru", 390, "GR-BRU-001", {"weight": "200g", "blend": "70% Coffee, 30% Chicory"}),
    ("Dabur Honey 100% Pure Squeezy Pack 400g", "Dabur", 195, "GR-DAB-001", {"weight": "400g", "sugar_free": "No Added Sugar"}),
    ("Dabur Chyawanprash 2X Immunity Booster 1kg", "Dabur", 395, "GR-DAB-002", {"weight": "1kg", "herbs": "Amla & 40+ Ayurvedic Herbs"}),
    ("Saffola Gold Pro Healthy Heart Edible Oil 5L Jar", "Saffola", 895, "GR-SAF-001", {"volume": "5L", "blend": "Rice Bran and Sunflower Oil"}),
    ("Saffola Masala Oats Classic Masala 1kg Saver Pack", "Saffola", 199, "GR-SAF-002", {"weight": "1kg", "fiber": "High Dietary Fiber"}),
    ("Daawat Rozana Gold Basmati Rice 5kg", "Daawat", 449, "GR-DAA-001", {"weight": "5kg", "aging": "Aged 1 Year"}),
    ("Daawat Biryani World's Longest Grain Basmati 1kg", "Daawat", 215, "GR-DAA-002", {"weight": "1kg", "elongation": "2.5x Post Cooking"}),
    ("Catch Sprinklers Table Salt & Black Pepper Combo", "Catch", 120, "GR-CAT-001", {"pieces": 2, "rotary_table": True}),
    ("Catch Chatpata Sabzi Masala 100g", "Catch", 65, "GR-CAT-002", {"weight": "100g", "flavor": "Home Style"}),
    ("Kissan Fresh Mixed Fruit Jam 1kg Glass Bottle", "Kissan", 295, "GR-KIS-001", {"weight": "1kg", "fruits": "8 Real Fruit Pulps"}),
    ("Kissan Fresh Tomato Ketchup Sweet & Tangy 1.2kg", "Kissan", 155, "GR-KIS-002", {"weight": "1.2kg", "tomatoes": "100% Real Juicy Tomatoes"}),
    ("Real Fruit Power Mixed Fruit Juice 1L Tetra", "Real", 115, "GR-REA-001", {"volume": "1L", "preservatives": False}),
    ("Real Fruit Power Alphonso Mango Nectar 1L", "Real", 125, "GR-REA-002", {"volume": "1L", "mango": "Ratnagiri Alphonso"}),
    ("Kellogg's Corn Flakes Original Crisp Cereal 1.2kg", "Kelloggs", 365, "GR-KEL-001", {"weight": "1.2kg", "iron": "Enriched with 8 Vitamins"}),
    ("Kellogg's Chocos Crunchy Cocoa Shells 1.2kg", "Kelloggs", 410, "GR-KEL-002", {"weight": "1.2kg", "wheat": "Solid Wheat Goodness"}),
    ("Quaker Rolled Oats 100% Wholegrain 1kg Pouch", "Quaker", 195, "GR-QUA-001", {"weight": "1kg", "beta_glucan": "Lowers Cholesterol"}),
    ("Patanjali Cow's Ghee Pure Desi 1L Carton", "Patanjali", 590, "GR-PAT-001", {"volume": "1L", "ayurvedic": True}),
    ("Patanjali Traditional Dant Kanti Toothpaste 200g", "Patanjali", 110, "GR-PAT-002", {"weight": "200g", "herbal": True}),
    ("Cadbury Dairy Milk Silk Chocolate Bar 150g", "Cadbury", 175, "GR-CAD-001", {"weight": "150g", "smoothness": "Classic Silk"}),
    ("Cadbury Bournvita Chocolate Health Drink Refill 1kg", "Cadbury", 415, "GR-CAD-002", {"weight": "1kg", "vitamins": "Vitamin D and Calcium"}),
    ("Horlicks Classic Malt Health Drink Jar 1kg", "Horlicks", 440, "GR-HOR-001", {"weight": "1kg", "clinically_proven": True}),
    ("Red Label Strong Blend CTC Leaf Tea 1kg", "Red Label", 460, "GR-RED-001", {"weight": "1kg", "taste": "Swad Apnepann Ka"}),
    ("Taj Mahal Fine Selection Darjeeling & Assam Tea 500g", "Taj Mahal", 380, "GR-TAJ-001", {"weight": "500g", "flavor": "Wah Taj Master Blend"}),
    ("Ching's Secret Schezwan Chutney Dip & Cook 250g", "Chings", 85, "GR-CHI-001", {"weight": "250g", "spiciness": "Fiery Desi Chinese"}),
    ("Ching's Secret Hakka Eggless Noodles 600g Family", "Chings", 95, "GR-CHI-002", {"weight": "600g", "boil_time": "4 mins"}),
    ("Nutella Hazelnut Cocoa Spread 350g Jar", "Nutella", 385, "GR-NUT-001", {"weight": "350g", "origin": "Imported Hazelnuts"}),
    ("Sundrop Superlite Advanced Sunflower Oil 5L Can", "Sundrop", 870, "GR-SUN-001", {"volume": "5L", "absorb": "Low Absorption Technology"}),
    ("24 Mantra Organic Raw Brown Sugar 1kg", "24 Mantra", 125, "GR-24M-001", {"weight": "1kg", "organic": True, "unrefined": True}),
    ("24 Mantra Organic Cold Pressed Sesame Til Oil 500ml", "24 Mantra", 240, "GR-24M-002", {"volume": "500ml", "organic": True}),
]

FASHION_DATA = [
    ("Allen Solly Men's Slim Fit Casual Cotton Shirt", "Allen Solly", 1499, "FA-ALL-001", {"fabric": "100% Cotton", "fit": "Slim", "pattern": "Solid"}),
    ("Allen Solly Women's Relaxed Fit Trouser Pants", "Allen Solly", 1699, "FA-ALL-002", {"fabric": "Poly-Viscose", "waist": "Mid-Rise"}),
    ("Allen Solly Textured Formal Leather Belt for Men", "Allen Solly", 899, "FA-ALL-003", {"material": "Genuine Leather", "color": "Dark Brown"}),
    ("Peter England Men's Regular Fit Formal Dress Shirt", "Peter England", 1099, "FA-PET-001", {"fit": "Regular", "collar": "Spread Collar"}),
    ("Peter England Men's Flat-Front Poly-Wool Trousers", "Peter England", 1399, "FA-PET-002", {"fit": "Slim Fit", "color": "Charcoal Grey"}),
    ("Peter England 2-Piece Classic Navy Notch Lapel Suit", "Peter England", 6999, "FA-PET-003", {"pieces": 2, "lapel": "Notch", "color": "Navy Blue"}),
    ("Levi's 511 Men's Slim Fit Mid-Rise Stretch Jeans", "Levi's", 2799, "FA-LEV-001", {"denim": "99% Cotton 1% Elastane", "wash": "Dark Indigo"}),
    ("Levi's 501 Original Straight Fit Heavyweight Jeans", "Levi's", 3999, "FA-LEV-002", {"closure": "Button Fly", "fit": "Straight Leg"}),
    ("Levi's Housemark Pure Cotton Graphic T-Shirt", "Levi's", 999, "FA-LEV-003", {"neck": "Crew Neck", "sleeve": "Short Sleeve"}),
    ("Levi's Genuine Reversible Leather Belt (Black/Tan)", "Levi's", 1299, "FA-LEV-004", {"buckle": "Rotary Reversible", "width": "35mm"}),
    ("Biba Women's Printed Straight Cotton Kurta", "Biba", 1599, "FA-BIB-001", {"fabric": "Pure Cotton", "length": "Calf Length", "sleeve": "3/4th"}),
    ("Biba Festive Anarkali Kurta with Dupatta Set", "Biba", 3499, "FA-BIB-002", {"embroidery": "Zari Work", "pieces": 3, "occasion": "Festive"}),
    ("Biba Women's Regular Fit Rayon Palazzo Pants", "Biba", 999, "FA-BIB-003", {"waist": "Elasticated Drawstring", "color": "Off White"}),
    ("W for Woman Eclectic Bandhani Print A-Line Kurta", "W", 1799, "FA-WWO-001", {"print": "Bandhani Inspired", "neck": "Mandarin Collar"}),
    ("W for Woman Solid Crop Top and Dhoti Skirt Set", "W", 2899, "FA-WWO-002", {"silhouette": "Contemporary Fusion", "color": "Mustard Yellow"}),
    ("W for Woman Slim Fit Churidar Leggings", "W", 799, "FA-WWO-003", {"stretch": "4-Way Lycra Cotton", "color": "Ruby Red"}),
    ("Nike Air Monarch IV Men's Training Sneakers", "Nike", 4995, "FA-NIK-001", {"sole": "Phylon Air-Sole", "closure": "Lace-Up"}),
    ("Nike Revolution 7 Men's Road Running Shoes", "Nike", 3695, "FA-NIK-002", {"upper": "Breathable Mesh", "cushioning": "Soft Foam"}),
    ("Nike Dri-FIT Men's Moisture-Wicking Sports Tee", "Nike", 1795, "FA-NIK-003", {"technology": "Dri-FIT", "fit": "Standard Athletic"}),
    ("Nike Club Fleece Brushed French Terry Joggers", "Nike", 2995, "FA-NIK-004", {"waist": "Drawstring Elastic", "pockets": "Side Hand"}),
    ("Puma Smashic Unisex Classic Low-Top Sneakers", "Puma", 2299, "FA-PUM-001", {"upper": "Synthetic Leather", "insole": "SoftFoam+"}),
    ("Puma Darter Pro Lightweight Running Shoes", "Puma", 3199, "FA-PUM-002", {"cushion": "ProFoam EVA", "weight": "Ultra Light"}),
    ("Puma Men's Regular Fit Cotton Training Track Pants", "Puma", 1599, "FA-PUM-003", {"color": "Puma Black", "logo": "Cat Logo Print"}),
    ("Puma Unisex Phase Backpack 22L Water-Resistant", "Puma", 1199, "FA-PUM-004", {"capacity": "22L", "compartments": 2}),
    ("Titan Workwear Men's Stainless Steel Dial Watch", "Titan", 3995, "FA-TIT-001", {"movement": "Quartz", "water_resistance": "50m", "strap": "Stainless Steel"}),
    ("Titan Raga Viva Analog Mother of Pearl Women's Watch", "Titan", 4495, "FA-TIT-002", {"dial": "Mother of Pearl", "strap": "Rose Gold Metal"}),
    ("Titan Neo Splash Men's Multi-Function Chronograph", "Titan", 6795, "FA-TIT-003", {"sub_dials": 3, "case": "Mineral Glass"}),
    ("Fastrack Limitless FS1 Smartwatch 1.95-inch Display", "Fastrack", 1995, "FA-FAS-001", {"bt_calling": True, "sports_modes": "100+"}),
    ("Fastrack Casual Black Dial Analog Watch for Men", "Fastrack", 1495, "FA-FAS-002", {"strap": "Silicone Rubber", "warranty": "2 Years"}),
    ("Fastrack Pilot UV-Protected Unisex Aviator Sunglasses", "Fastrack", 1295, "FA-FAS-003", {"uv_protection": "100% UV400", "frame": "Metal Alloy"}),
    ("FabIndia Handblock Printed Pure Chanderi Saree", "FabIndia", 4999, "FA-FAB-001", {"fabric": "Silk Cotton Chanderi", "blouse": "Unstitched Piece Included"}),
    ("FabIndia Men's Pure Linen Long Kurta with Pockets", "FabIndia", 2599, "FA-FAB-002", {"fabric": "100% Breathable Linen", "color": "Pastel Olive"}),
    ("FabIndia Artisanal Handwoven Jute Tote Bag", "FabIndia", 1499, "FA-FAB-003", {"handle": "Genuine Leather Straps", "craft": "Handmade"}),
    ("Manyavar Men's Jacquard Kurta Pajama Wedding Set", "Manyavar", 3999, "FA-MAN-001", {"fabric": "Art Silk Jacquard", "occasion": "Haldi and Sangeet"}),
    ("Manyavar Embroidered Nehru Modi Jacket for Men", "Manyavar", 2499, "FA-MAN-002", {"pattern": "Floral Threadwork", "buttons": "Metallic Shank"}),
    ("Mohey Women's Embroidered Georgette Lehanga Choli", "Manyavar", 9999, "FA-MOH-001", {"work": "Sequins & Resham", "dupatta": "Net with Border"}),
    ("Bata Comfit Men's Formal Slip-On Loafers", "Bata", 1699, "FA-BAT-001", {"upper": "Genuine Leather", "comfort": "Memory Foam"}),
    ("Bata Sunshine Women's Wedge Heeled Comfort Sandals", "Bata", 1199, "FA-BAT-002", {"heel_height": "2.5 inches", "cushioning": "Soft Footbed"}),
    ("Hush Puppies Men's Classic Derby Leather Shoes", "Hush Puppies", 4499, "FA-HUS-001", {"upper": "Full Grain Crust Leather", "sole": "Flexible Rubber"}),
    ("Crocs Classic Unisex Lightweight Foam Clogs", "Crocs", 2995, "FA-CRO-001", {"material": "Croslite Foam", "water_friendly": True}),
    ("Wildcraft 45L Rucksack Trekking Travel Backpack", "Wildcraft", 2999, "FA-WIL-001", {"volume": "45L", "rain_cover": True, "back_support": "Ergonomic"}),
    ("Wildcraft Hypadry Waterproof Men's Raincoat Jacket", "Wildcraft", 1899, "FA-WIL-002", {"waterproof": "Up to 2000mm", "hood": "Adjustable"}),
    ("Van Heusen Men's Formal Regular Fit Solid Trouser", "Van Heusen", 1799, "FA-VAN-001", {"stretch": "AutoFlex Waistband", "color": "Navy"}),
    ("Van Heusen Antibacterial Combed Cotton Boxer Briefs (Pack of 2)", "Van Heusen", 699, "FA-VAN-002", {"pack": 2, "anti_odor": True}),
    ("Jockey 100% Combed Cotton Men's Round Neck Undershirt (Pack of 3)", "Jockey", 599, "FA-JOC-001", {"pack": 3, "yarn": "Super Combed Rib"}),
    ("Jockey Cotton Stretch Women's Gym Workout Leggings", "Jockey", 999, "FA-JOC-002", {"waist": "Broad Elastic", "fit": "Skinny Ankle Length"}),
    ("Sparx Men's Mesh Lightweight Running Sports Shoes", "Sparx", 999, "FA-SPA-001", {"sole": "Lightweight EVA", "color": "Grey Orange"}),
    ("Campus Oxyfit Men's Walking & Gym Sneakers", "Campus", 1249, "FA-CAM-001", {"insole": "Memory Foam Pillows", "upper": "Knitted Mesh"}),
    ("Red Tape Men's Classic Casual Lifestyle Sneaker", "Red Tape", 1599, "FA-RED-001", {"upper": "Synthetic PU", "sole": "TPR Grip"}),
    ("Lenskart Air Rimless Lightweight Flexible Eyeglasses", "Lenskart", 1999, "FA-LEN-001", {"weight": "11 grams", "frame": "Titanium Alloy"}),
    ("Vincent Chase Polarized Classic Wayfarer Sunglasses", "Lenskart", 999, "FA-VIN-001", {"polarized": True, "uv": "UV400"}),
    ("Caprese Faux Leather Handbag for Women", "Caprese", 2499, "FA-CAP-001", {"compartments": 3, "strap": "Detachable Sling"}),
    ("Lavie Women's Betula Structured Tote Bag", "Lavie", 1899, "FA-LAV-001", {"finish": "Saffiano Textured", "color": "Ochre Yellow"}),
    ("Skybags Trooper 55cm Polycarbonate Cabin Luggage Trolley", "Skybags", 2799, "FA-SKY-001", {"wheels": "4 Spinner 360", "lock": "Fixed Number Lock"}),
    ("American Tourister Ivy 68cm Check-in Medium Suitcase", "American Tourister", 3999, "FA-AMT-001", {"material": "Scratch Resistant Polypropylene", "capacity": "66L"}),
    ("Safari Pentagon 3-Piece Hardsided Luggage Set (S/M/L)", "Safari", 6499, "FA-SAF-001", {"set": "Cabin + Medium + Large", "warranty": "3 Years"}),
    ("VIP Tuscany Polyester Softsided Expandable Trolley 65cm", "VIP", 3299, "FA-VIP-001", {"expandable": True, "corners": "Corner Guards"}),
    ("Zaveri Pearls Gold-Plated Kundan Choker Necklace Set", "Zaveri Pearls", 699, "FA-ZAV-001", {"gemstones": "Faux Pearls & Kundan", "earrings": "Matching Jhumkas"}),
    ("Sukkhi Traditional Austrian Diamond Bangles (Set of 4)", "Sukkhi", 499, "FA-SUK-001", {"plating": "Micro Gold Plating", "pieces": 4}),
    ("Voylla Men's Oxidized Silver Kada Bracelet with Rudraksha", "Voylla", 799, "FA-VOY-001", {"material": "Brass with Silver Finish", "stone": "Original Rudraksha"}),
]

HOME_DATA = [
    ("Prestige Svachh Deluxe Alpha Stainless Steel Pressure Cooker 3L", "Prestige", 2450, "HO-PRE-001", {"capacity": "3L", "spillage_control": True, "induction": True}),
    ("Prestige Iris Plus 750W Mixer Grinder with 3 SS Jars", "Prestige", 2999, "HO-PRE-002", {"motor": "750 Watts", "jars": "3 Stainless Steel + 1 Juicer"}),
    ("Prestige Omega Deluxe Granite Induction Base Dosa Tawa 280mm", "Prestige", 995, "HO-PRE-003", {"coating": "5-Layer Non-Stick", "diameter": "28cm"}),
    ("Prestige Electric Kettle 1.5L Stainless Steel Body", "Prestige", 749, "HO-PRE-004", {"capacity": "1.5L", "auto_cutoff": True, "power": "1500W"}),
    ("Hawkins Contura Hard Anodized Inner Lid Cooker 5L", "Hawkins", 2750, "HO-HAW-001", {"capacity": "5L", "material": "Hard Anodized", "corrosion_resistant": True}),
    ("Hawkins Futura Non-Stick Deep Kadhai with Glass Lid 2.5L", "Hawkins", 1850, "HO-HAW-002", {"capacity": "2.5L", "handles": "Stay Cool Rosewood"}),
    ("Hawkins Stainless Steel Tea Pan with Glass Lid 1.5L", "Hawkins", 975, "HO-HAW-003", {"capacity": "1.5L", "spout": "Drip Free Pouring"}),
    ("Pigeon by Stovekraft 2-Burner Glass Top Gas Stove", "Pigeon", 1999, "HO-PIG-001", {"burners": "Brass High Efficiency", "top": "Toughened Black Glass"}),
    ("Pigeon Handy Mini Plastic Chopper with 3 Blades", "Pigeon", 249, "HO-PIG-002", {"blades": "Stainless Steel 3-Blade", "pull_cord": True}),
    ("Pigeon Cruise 1800W Induction Cooktop with Preset Menus", "Pigeon", 1499, "HO-PIG-003", {"power": "1800W", "display": "LED with Timer"}),
    ("Milton Thermosteel Flip Lid Insulated Stainless Steel Bottle 1L", "Milton", 895, "HO-MIL-001", {"capacity": "1000ml", "insulation": "24h Hot and Cold"}),
    ("Milton Executive Stainless Steel Insulated Lunch Box with Bag", "Milton", 945, "HO-MIL-002", {"containers": "3 SS Containers", "pouch": "Thermal Insulated"}),
    ("Milton Spotzero Zero Dust Microfiber Floor Mop", "Milton", 799, "HO-MIL-003", {"handle": "Extendable 360 Degree", "microfiber": True}),
    ("Milton Plastic Airtight Dry Fruit & Kitchen Container Set of 6", "Milton", 449, "HO-MIL-004", {"pieces": 6, "bpa_free": True, "capacity": "600ml each"}),
    ("Borosil Klip N Store Microwavable Borosilicate Glass Bowls (Set of 3)", "Borosil", 995, "HO-BOR-001", {"oven_safe": "Up to 400C", "pieces": 3, "airtight": True}),
    ("Borosil Vision Classic Thin Tea Glasses (Pack of 6)", "Borosil", 425, "HO-BOR-002", {"pieces": 6, "thermal_shock": "100% Flame Proof"}),
    ("Borosil Pronto Stainless Steel Electric Hand Blender 300W", "Borosil", 1290, "HO-BOR-003", {"motor": "300W DC", "shaft": "Detachable SS Blade"}),
    ("Bombay Dyeing 100% Cotton 144TC King Size Double Bedsheet with 2 Pillows", "Bombay Dyeing", 1199, "HO-BOM-001", {"thread_count": 144, "size": "274x274 cm", "pattern": "Floral Botanical"}),
    ("Bombay Dyeing Super Soft Cotton Bath Towel 500 GSM", "Bombay Dyeing", 549, "HO-BOM-002", {"gsm": 500, "material": "100% Combed Terry Cotton"}),
    ("Bombay Dyeing Microfiber Lightweight Reversible All-Season AC Quilt Comforter", "Bombay Dyeing", 1899, "HO-BOM-003", {"filling": "Siliconized Microfiber 200 GSM", "size": "Double Bed"}),
    ("Tupperware Aquasafe 1L Round Flip-Top Water Bottles (Set of 4)", "Tupperware", 1099, "HO-TUP-001", {"pieces": 4, "spill_proof": True, "bpa_free": True}),
    ("Tupperware Modular Spice Shakers and Mates (Set of 4)", "Tupperware", 749, "HO-TUP-002", {"seals": "Dual Pour Dispenser", "airtight": True}),
    ("Wonderchef Nutri-Blend 400W Mixer Grinder Blender with 2 Unbreakable Jars", "Wonderchef", 2499, "HO-WON-001", {"rpm": "22000 RPM", "jars": "2 Polycarbonate"}),
    ("Wonderchef Sanjeev Kapoor Tandoor Standard Electric Grill", "Wonderchef", 4299, "HO-WON-002", {"thermostat": "Adjustable Temperature", "oil_free": True}),
    ("Cello Opalware Dazzle Tropical Dinner Set 35 Pieces", "Cello", 2999, "HO-CEL-001", {"pieces": 35, "break_resistant": True, "dishwasher_safe": True}),
    ("Cello Venice Plastic Bathroom Bucket and Tub Combo 5-Piece", "Cello", 799, "HO-CEL-002", {"set": "Bucket 20L + Basin + Stool + Mug", "frost_finish": True}),
    ("Bajaj Rex 500W Mixer Grinder with Nutri-Pro Feature", "Bajaj", 1999, "HO-BAJ-001", {"motor": "500 Watts", "blades": "Multi-Function Stainless Steel"}),
    ("Bajaj DX-7 1000W Lightweight Dry Iron with Non-Stick Golden Soleplate", "Bajaj", 799, "HO-BAJ-002", {"power": "1000W", "soleplate": "German Coating"}),
    ("Bajaj New Shakti 15L Storage Water Heater Geyser (4-Star)", "Bajaj", 6299, "HO-BAJ-003", {"capacity": "15L", "tank": "Titanium Armour Technology"}),
    ("Usha Mist Air Icy 400mm 55W Pedestal Fan with Remote", "Usha", 2899, "HO-USH-001", {"speed": "1280 RPM", "sweep": "400mm", "remote": True}),
    ("Usha EI 1602 1000W Lightweight Dry Iron with Cord Swivel", "Usha", 699, "HO-USH-002", {"soleplate": "Non-Stick Weilburger", "thermostat": True}),
    ("Crompton Ozone 75L Desert Air Cooler with Honeycomb Cooling Pads", "Crompton", 9499, "HO-CRO-001", {"tank": "75L", "throw": "52 Feet", "inverter_compatible": True}),
    ("Crompton Amica 15L 5-Star Storage Water Heater Geyser", "Crompton", 6899, "HO-CRO-002", {"element": "Incoloy 800", "pressure": "8 Bar High Rise Suitable"}),
    ("Philips Daily Collection HD9218 1425W Rapid Air Technology Air Fryer", "Philips", 6499, "HO-PHI-001", {"oil_reduction": "Up to 90% Less Fat", "capacity": "4.1L"}),
    ("Philips Steam Iron GC1905 with Fast Water Filling and Continuous Steam", "Philips", 1495, "HO-PHI-002", {"power": "1440W", "steam": "13g/min Continuous"}),
    ("Morphy Richards Europa 800W Espresso & Cappuccino Coffee Maker with Milk Frother", "Morphy", 4299, "HO-MOR-001", {"pressure": "4 Bar Steam", "frother": "Turbo Steam Wand"}),
    ("Morphy Richards 24L Convection Microwave Oven with 300 Auto Cook Menus", "Morphy", 11499, "HO-MOR-002", {"capacity": "24L", "baking": True}),
    ("Eureka Forbes Quick Clean DX 1200W Portable Canister Vacuum Cleaner", "Eureka", 3699, "HO-EUR-001", {"suction": "1900mm of WC", "dust_bag": "Indicator Available"}),
    ("Aquaguard Sure Delight NXT RO+UV+Taste Adjuster Water Purifier 6L", "Eureka", 8499, "HO-EUR-002", {"purification": "RO+UV+MTDS", "stages": 7}),
    ("Livpure Glo Star RO+In-Tank UV Mineraliser Water Purifier 7L", "Livpure", 7499, "HO-LIV-001", {"capacity": "7L", "filtration": "Insect Proof Sealed Tank"}),
    ("Kent Grand Plus RO+UV+UF+TDS Controller Mineral Water Purifier 9L", "Kent", 14999, "HO-KEN-001", {"technology": "Zero Water Wastage", "uv_led": True}),
    ("Wakefit Orthopedic Memory Foam 6-inch King Size Mattress (78x72 inch)", "Wakefit", 12499, "HO-WAK-001", {"warranty": "10 Years", "zones": "Differential Pressure Support"}),
    ("Wakefit Hollow Fiber Sleeping Pillows (Set of 2)", "Wakefit", 799, "HO-WAK-002", {"fill": "200 GSM Microfiber", "hypoallergenic": True}),
    ("SleepyCat Original 3-Layer Orthopedic Medium-Firm Mattress Double", "SleepyCat", 9999, "HO-SLE-001", {"cover": "Bamboo Zipper Washable", "cooling": "Aeroflow Foam"}),
    ("Solimo Solid Sheesham Wood 4-Seater Dining Table with Chairs", "Solimo", 14999, "HO-SOL-001", {"wood": "100% Solid Indian Rosewood", "finish": "Teak Polish"}),
    ("Solimo Microfiber 1200 GSM Thick Reversible Bath Mat Set of 2", "Solimo", 499, "HO-SOL-002", {"anti_skid": "Latex Rubber Backing", "pieces": 2}),
    ("Spaces Hygro Cotton Bath Towels 600 GSM Ultra Absorbent (Pack of 2)", "Spaces", 1299, "HO-SPA-001", {"gsm": 600, "technology": "Blooms After Wash"}),
    ("Trident Indulgence 100% Egyptian Cotton Luxury Bath Sheet 700 GSM", "Trident", 899, "HO-TRI-001", {"gsm": 700, "cotton": "Long Staple Egyptian"}),
    ("Spotzero by Milton Elite Spin Mop with Big Wheels and SS Basket", "Milton", 1199, "HO-MIL-005", {"basket": "Stainless Steel Spinner", "drain_spout": True}),
    ("Scotch-Brite Sponge Wipe Cellulose Reusable Kitchen Cleaning (Pack of 5)", "Scotch-Brite", 210, "HO-SCO-001", {"absorption": "10x Weight in Water", "pack": 5}),
]

PERSONAL_CARE_DATA = [
    ("Dove Intense Repair Shampoo with Keratin Actives 650ml", "Dove", 575, "PC-DOV-001", {"volume": "650ml", "benefits": "Nourishes Heat Damaged Hair"}),
    ("Dove Cream Beauty Bathing Soap Bar (Pack of 5 x 100g)", "Dove", 310, "PC-DOV-002", {"pack": 5, "moisturizer": "1/4th Moisturizing Cream"}),
    ("Dove Deep Moisture Body Wash Shower Gel 800ml Pump", "Dove", 465, "PC-DOV-003", {"sulfate_free": True, "skin_type": "Dry Sensitive"}),
    ("Nivea Soft Light Moisturizing Cream with Vitamin E & Jojoba 300ml", "Nivea", 399, "PC-NIV-001", {"volume": "300ml", "texture": "Non-Greasy Whipped"}),
    ("Nivea Men Fresh Active Deodorant Spray 48h Protection 150ml", "Nivea", 215, "PC-NIV-002", {"volume": "150ml", "scent": "Ocean Extracts"}),
    ("Nivea Sun Protect & Moisture SPF 50 PA+++ Sunscreen Lotion 125ml", "Nivea", 475, "PC-NIV-003", {"spf": "50 PA+++", "water_resistant": True}),
    ("Nivea Lip Care Hydro Care SPF 15 Lip Balm with Pure Aloe", "Nivea", 160, "PC-NIV-004", {"spf": 15, "flavor": "Aloe Vera"}),
    ("Himalaya Purifying Neem Face Wash for Acne & Pimple Control 400ml", "Himalaya", 345, "PC-HIM-001", {"volume": "400ml", "herbs": "Neem and Turmeric"}),
    ("Himalaya Anti-Hair Fall Bhringaraja Hair Oil 200ml", "Himalaya", 185, "PC-HIM-002", {"volume": "200ml", "ingredients": "Bhringaraja & Amla"}),
    ("Himalaya Herbals Nourishing Skin Cream with Aloe & Winter Cherry 200ml", "Himalaya", 195, "PC-HIM-003", {"volume": "200ml", "winter_care": True}),
    ("Himalaya Complete Care Herbal Toothpaste with Neem & Pomegranate 150g", "Himalaya", 115, "PC-HIM-004", {"weight": "150g", "gum_protection": True}),
    ("Biotique Bio Kelp Protein Shampoo for Falling Hair Treatment 650ml", "Biotique", 449, "PC-BIO-001", {"ayurvedic": True, "therapeutic": "Stimulates Scalp"}),
    ("Biotique Bio Dandelion Visibly Ageless Botanical Serum 190ml", "Biotique", 480, "PC-BIO-002", {"herbal": "Pure Dandelion & Nutmeg"}),
    ("Biotique Morning Nectar Flawless Skin Lotion with Honey 400ml", "Biotique", 299, "PC-BIO-003", {"volume": "400ml", "skin_lightening": False}),
    ("Mamaearth Onion Hair Oil with Redensyl for Hair Regrowth 250ml", "Mamaearth", 499, "PC-MAM-001", {"toxin_free": "No Parabens No Silicones", "active": "Redensyl"}),
    ("Mamaearth Ubtan Natural Face Wash with Turmeric and Saffron 150ml", "Mamaearth", 259, "PC-MAM-002", {"tan_removal": True, "dermatologically_tested": True}),
    ("Mamaearth Vitamin C Daily Glow Light Face Cream 80g", "Mamaearth", 249, "PC-MAM-003", {"antioxidant": "Vitamin C and Turmeric"}),
    ("Mamaearth Milky Soft Gentle Baby Shampoo for Newborns 400ml", "Mamaearth", 399, "PC-MAM-004", {"tear_free": True, "oats_milk": True}),
    ("Wild Stone Edge Ultra Sensual Long-Lasting Eau De Parfum 100ml", "Wild Stone", 499, "PC-WIL-001", {"type": "Eau De Parfum", "notes": "Woody Marine Citrus"}),
    ("Wild Stone Forest Spice Talcum Powder for Men 300g", "Wild Stone", 145, "PC-WIL-002", {"weight": "300g", "fragrance": "Masculine Woody"}),
    ("Wild Stone Ultra Sensual No Gas Luxury Deodorant Body Spray 120ml", "Wild Stone", 249, "PC-WIL-003", {"no_gas": True, "sprays": "1000+ Sprays"}),
    ("Park Avenue Voyage Signature No Gas Luxury Perfume Body Spray 150ml", "Park Avenue", 270, "PC-PAR-001", {"scent": "Citrus Mandarin Amber"}),
    ("Park Avenue Good Morning Ultimate After Shave Lotion 100ml", "Park Avenue", 195, "PC-PAR-002", {"cooling": "Menthol and Aloe"}),
    ("Park Avenue Beer Shampoo for Shiny Voluminous Hair 370ml", "Park Avenue", 290, "PC-PAR-003", {"hops_barley": True, "shine": "Bio-Keratin"}),
    ("Dettol Original Germ Protection Antibacterial Bathing Soap (Pack of 5 x 125g)", "Dettol", 285, "PC-DET-001", {"protection": "100% Better Germ Defense"}),
    ("Dettol Liquid Handwash Refill Pouch Original Pine 1500ml", "Dettol", 235, "PC-DET-002", {"volume": "1.5L", "antiseptic": True}),
    ("Lifebuoy Total 10 Antibacterial Germ Defense Soap Bar (Pack of 4 x 125g)", "Lifebuoy", 165, "PC-LIF-001", {"silver_shield": True, "pack": 4}),
    ("Lifebuoy Total 10 Sanitizer Bottle with 70% Alcohol 500ml", "Lifebuoy", 199, "PC-LIF-002", {"alcohol_content": "70% v/v"}),
    ("Head & Shoulders Cool Menthol Anti-Dandruff Shampoo 650ml", "Head & Shoulders", 599, "PC-HNS-001", {"active": "Zinc Pyrithione", "cooling": "Fresh Menthol"}),
    ("Head & Shoulders Smooth & Silky Anti-Dandruff 2-in-1 Conditioner 340ml", "Head & Shoulders", 399, "PC-HNS-002", {"formula": "HydraZinc Moisturizing"}),
    ("Tresemme Keratin Smooth Salon-Quality Shampoo with Argan Oil 580ml", "Tresemme", 520, "PC-TRE-001", {"benefits": "Frizz Resistance for 72 Hours"}),
    ("Tresemme Keratin Smooth Deep Nourishing Hair Conditioner 340ml", "Tresemme", 365, "PC-TRE-002", {"keratin": True, "sulfate_control": True}),
    ("Parachute 100% Pure Unrefined Coconut Hair Oil 500ml Bottle", "Parachute", 210, "PC-PAR-004", {"edible_grade": True, "filter": "5-Stage Purification"}),
    ("Parachute Advansed Ayurvedic Deep Conditioning Hair Oil 300ml", "Parachute", 175, "PC-PAR-005", {"herbs": "21 Essential Ayurvedic Extracts"}),
    ("Bajaj Almond Drops Non-Sticky Hair Oil with 6X Vitamin E 500ml", "Bajaj", 325, "PC-BAJ-004", {"non_sticky": True, "vitamin_e": "6X Nourishment"}),
    ("Gillette Fusion5 ProGlide Men's Razor with FlexBall Technology", "Gillette", 899, "PC-GIL-001", {"blades": "5 Anti-Friction Blades", "flexball": True}),
    ("Gillette Classic Sensitive Skin Shaving Foam 418g Big Can", "Gillette", 249, "PC-GIL-002", {"comfort": "Aloe Vera Soothing Formula"}),
    ("Colgate MaxFresh Spicy Fresh Red Gel Toothpaste with Cooling Crystals 300g (Pack of 2)", "Colgate", 225, "PC-COL-001", {"flavor": "Spicy Clove and Menthol", "pack": 2}),
    ("Colgate Strong Teeth Calcium Boost Dental Toothpaste 500g Value Saver", "Colgate", 260, "PC-COL-002", {"fluoride": "Amino Shakti Technology"}),
    ("Sensodyne Fresh Mint Sensitive Teeth Relief Daily Toothpaste 150g", "Sensodyne", 240, "PC-SEN-001", {"sensitivity": "Clinically Proven 24/7 Relief"}),
]

CATEGORY_MAP = {
    "electronics": (ELECTRONICS_DATA, "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80"),
    "grocery": (GROCERY_DATA, "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&q=80"),
    "fashion": (FASHION_DATA, "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=500&q=80"),
    "home": (HOME_DATA, "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=500&q=80"),
    "personal_care": (PERSONAL_CARE_DATA, "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=500&q=80"),
}


async def seed():
    pg_url = os.getenv("PG_URL")
    if not pg_url:
        raise ValueError("PG_URL environment variable is missing")
    pg_url = pg_url.replace("postgres://", "postgresql://")

    print("Connecting to PostgreSQL at Aiven...")
    conn = await asyncpg.connect(pg_url, ssl="require")

    # 1. Insert Demo Customer
    demo_cust_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    await conn.execute(
        """
        INSERT INTO customers (id, email, name, phone, created_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name, phone = EXCLUDED.phone
        """,
        demo_cust_id,
        "demo@mystore.in",
        "Priya Sharma",
        "+91-9876543210",
    )
    print("Demo customer seeded (Priya Sharma).")

    # 2. Gather products
    total_products = []
    for cat_name, (items, default_img) in CATEGORY_MAP.items():
        for name, brand, price, sku, attrs in items:
            total_products.append({
                "id": uuid.uuid4(),
                "sku": sku,
                "name": name,
                "brand": brand,
                "category": cat_name,
                "description": f"Authentic {name} by {brand}. Top quality product for Indian households with high reliability.",
                "price_inr": Decimal(price),
                "image_url": default_img,
                "attrs": attrs,
            })

    print(f"Prepared {len(total_products)} distinct products. Seeding into PostgreSQL...")

    # Upsert products
    product_records = []
    for p in total_products:
        product_records.append((
            p["id"],
            p["sku"],
            p["name"],
            p["brand"],
            p["category"],
            p["description"],
            p["price_inr"],
            p["image_url"],
            json.dumps(p["attrs"]),
        ))

    await conn.executemany(
        """
        INSERT INTO products (id, sku, name, brand, category, description, price_inr, image_url, attrs, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW(), NOW())
        ON CONFLICT (sku) DO UPDATE SET
            name = EXCLUDED.name,
            brand = EXCLUDED.brand,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            price_inr = EXCLUDED.price_inr,
            image_url = EXCLUDED.image_url,
            attrs = EXCLUDED.attrs,
            updated_at = NOW()
        """,
        product_records,
    )

    # Fetch inserted/existing products to get their true IDs
    rows = await conn.fetch("SELECT id, sku FROM products")
    sku_to_id = {r["sku"]: r["id"] for r in rows}

    # 3. Generate store stock across 5 cities
    random.seed(42)  # Deterministic seed for reproducible stock levels
    stock_records = []
    
    for i, p in enumerate(total_products):
        prod_id = sku_to_id[p["sku"]]
        
        # Determine city distribution
        # Special cases:
        # 1 item: completely out of stock in all cities (for demo)
        if i == 0:  # e.g., first item EL-SAM-001 is out of stock everywhere
            for city in CITIES:
                stock_records.append((prod_id, city, 0))
            continue
            
        # 1 item: exactly 1 unit left in Bengaluru for stress test demo!
        if i == 1:  # EL-SAM-002
            stock_records.append((prod_id, "Bengaluru", 1))
            stock_records.append((prod_id, "Mumbai", 0))
            stock_records.append((prod_id, "Delhi", 5))
            stock_records.append((prod_id, "Hyderabad", 0))
            stock_records.append((prod_id, "Chennai", 2))
            continue

        # Regular stock generation:
        chosen_cities = random.sample(CITIES, k=random.randint(3, 5))
        for city in chosen_cities:
            rand_val = random.random()
            if rand_val < 0.10:
                qty = 0  # 10% out of stock
            elif rand_val < 0.18:
                qty = random.randint(1, 3)  # low stock urgency
            else:
                qty = random.randint(15, 150)
            stock_records.append((prod_id, city, qty))

    print(f"Generated {len(stock_records)} store stock entries. Seeding into store_stock table...")

    await conn.executemany(
        """
        INSERT INTO store_stock (product_id, city, qty, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (product_id, city) DO UPDATE SET
            qty = EXCLUDED.qty,
            updated_at = NOW()
        """,
        stock_records,
    )

    # Verification count
    p_count = await conn.fetchval("SELECT count(*) FROM products")
    s_count = await conn.fetchval("SELECT count(*) FROM store_stock")
    c_count = await conn.fetchval("SELECT count(*) FROM customers")

    # 4. Seed Multi-Seller Marketplace Data (3 Sellers in Karnataka, Maharashtra, Delhi)
    print("Seeding marketplace sellers and multi-seller product offers...")
    SELLERS_DATA = [
        (
            uuid.UUID("10000000-0000-0000-0000-000000000001"),
            "MyStore Retail",
            "MYS",
            "29AABCM1234F1Z5",
            "Karnataka",
            "Warehouse 1, Electronic City, Bengaluru, Karnataka 560100"
        ),
        (
            uuid.UUID("20000000-0000-0000-0000-000000000002"),
            "Apex Global Traders",
            "APX",
            "27AAACA5678B1Z2",
            "Maharashtra",
            "Hub 4, Bhiwandi Logistics Park, Mumbai, Maharashtra 421302"
        ),
        (
            uuid.UUID("30000000-0000-0000-0000-000000000003"),
            "Capital Electronics Hub",
            "DEL",
            "07AAACD9012C1Z8",
            "Delhi",
            "Plot 12, Okhla Industrial Area Phase III, New Delhi, Delhi 110020"
        ),
    ]

    for s_id, s_name, s_code, s_gstin, s_state, s_addr in SELLERS_DATA:
        await conn.execute(
            """
            INSERT INTO sellers (id, name, seller_code, gstin, state, address, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                seller_code = EXCLUDED.seller_code,
                gstin = EXCLUDED.gstin,
                state = EXCLUDED.state,
                address = EXCLUDED.address
            """,
            s_id, s_name, s_code, s_gstin, s_state, s_addr
        )
        await conn.execute(
            """
            INSERT INTO seller_invoice_counters (seller_id, last_no)
            VALUES ($1, 0)
            ON CONFLICT (seller_id) DO NOTHING
            """,
            s_id
        )

    # 5. Seed seller_offers across the 3 sellers with differentiated pricing and stock
    prod_rows = await conn.fetch("SELECT id, price_inr FROM products")
    offers_records = []
    seller_ids = [s[0] for s in SELLERS_DATA]

    for pr in prod_rows:
        pid = pr["id"]
        base_price = Decimal(str(pr["price_inr"]))

        # For each city, generate offers across the 3 sellers
        for city in CITIES:
            # Seller 1: base price
            q1 = random.randint(10, 50)
            offers_records.append((pid, seller_ids[0], city, base_price, q1))

            # Seller 2: slightly cheaper or premium (+/- 2%)
            p2 = round(base_price * Decimal(str(random.choice([0.98, 0.99, 1.01, 1.02]))), 2)
            q2 = random.randint(5, 40)
            offers_records.append((pid, seller_ids[1], city, p2, q2))

            # Seller 3: varied price (+/- 3%)
            p3 = round(base_price * Decimal(str(random.choice([0.95, 0.97, 1.00, 1.03]))), 2)
            q3 = random.randint(0, 35)
            offers_records.append((pid, seller_ids[2], city, p3, q3))

    await conn.executemany(
        """
        INSERT INTO seller_offers (id, product_id, seller_id, city, price_inr, qty, created_at, updated_at)
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, NOW(), NOW())
        ON CONFLICT (product_id, seller_id, city) DO UPDATE SET
            price_inr = EXCLUDED.price_inr,
            qty = EXCLUDED.qty,
            updated_at = NOW()
        """,
        offers_records,
    )

    sellers_count = await conn.fetchval("SELECT count(*) FROM sellers")
    offers_count = await conn.fetchval("SELECT count(*) FROM seller_offers")

    print("\n--- SEED SUMMARY ---")
    print(f"Products in DB:    {p_count}")
    print(f"Stock entries:     {s_count}")
    print(f"Customers in DB:   {c_count}")
    print(f"Sellers in DB:     {sellers_count}")
    print(f"Seller offers:     {offers_count}")
    print("Done! All seed data successfully loaded.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())

