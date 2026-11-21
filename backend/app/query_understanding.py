"""Hinglish and Hindi (Devanagari) query understanding and normalizer module.

Accurately normalizes spoken and typed Hindi / Hinglish queries, translates Hindi
product terms and brand names to English catalog counterparts, strips conversational
fillers/stopwords, detects low-cost/budget intent, and extracts numeric price constraints.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Set

# Brand protection set (must never be mangled)
PROTECTED_BRANDS: Set[str] = {
    "samsung", "oneplus", "realme", "xiaomi", "boat", "jbl", "apple", "iphone", "lenovo", "hp", "sony",
    "noise", "portronics", "ambrane", "sandisk", "logitech", "tp-link", "fire-boltt",
    "zebronics", "boult", "evofox", "redragon", "crucial", "western digital", "seagate",
    "belkin", "anker", "amazon", "google", "ptron", "aashirvaad", "fortune", "tata", "mdh",
    "everest", "amul", "parle", "britannia", "maggi", "haldirams", "haldiram", "mtr", "nestle",
    "nescafe", "bru", "dabur", "saffola", "daawat", "catch", "kissan", "real", "kelloggs",
    "quaker", "patanjali", "cadbury", "horlicks", "red label", "taj mahal", "chings",
    "nutella", "sundrop", "24 mantra", "allen solly", "peter england", "levis", "levi's",
    "biba", "w", "nike", "puma", "titan", "fastrack", "fabindia", "manyavar", "mohey",
    "bata", "hush puppies", "crocs", "wildcraft", "van heusen", "jockey", "sparx", "campus",
    "red tape", "lenskart", "vincent chase", "caprese", "lavie", "skybags", "american tourister",
    "safari", "vip", "zaveri pearls", "sukkhi", "voylla", "prestige", "hawkins", "pigeon",
    "milton", "borosil", "bombay dyeing", "tupperware", "wonderchef", "cello", "bajaj",
    "usha", "crompton", "philips", "morphy richards", "eureka forbes", "aquaguard", "livpure",
    "kent", "wakefit", "sleepycat", "solimo", "spaces", "trident", "scotch-brite", "dove",
    "nivea", "himalaya", "biotique", "mamaearth", "wild stone", "park avenue", "dettol",
    "lifebuoy", "head & shoulders", "tresemme", "parachute", "gillette", "colgate", "sensodyne",
    "redmi", "vivo", "fogg", "engage", "bella vita", "lg"
}

# Conversational stopwords in Hindi & Hinglish that should be ignored during tokenization
HINDI_STOPWORDS: Set[str] = {
    # Hindi / Devanagari fillers
    "दिखाइए", "दिखाओ", "दिखाना", "दिखाएं", "दिखा", "बताइए", "बताओ", "खोजो", "ढूंढो", "ढूंढिए",
    "लाओ", "लाइए", "चाहिए", "देना", "दे दो", "दे", "दो", "करो", "कीजिए",
    "मुझे", "हमे", "हमको", "मेरे", "लिए", "वाला", "वाली", "वाले",
    "का", "की", "के", "में", "से", "को", "पर", "और", "या", "तक", "अंदर",
    "कम", "ज्यादा", "से कम", "से ज्यादा", "के अंदर",
    "रूपये", "रुपये", "रुपए", "रुपिया", "कहाँ", "कौन", "क्या", "है", "हैं", "था", "थी", "थे", "प्लीज", "जरा",
    # Hinglish fillers
    "dikhao", "dikhaye", "dikhana", "chahiye", "batao", "lao", "de", "do", "mujhe", "hame", "hamko", "mere", "liye",
    "wala", "wali", "wale", "karo", "please", "me", "mein", "se", "ko", "par", "hai", "hain", "ke", "ki", "ka",
    "bhi", "tha", "the", "thi", "kya", "andar", "tak", "kam", "jyada", "under", "below"
}

# Multi-word phrase mappings (Devanagari & Hinglish -> English catalog concepts)
PHRASE_MAPPINGS: dict[str, str] = {
    # Appliances
    "मिक्सर ग्राइंडर": "mixer grinder",
    "मिक्सी ग्राइंडर": "mixer grinder",
    "प्रेशर कुकर": "pressure cooker",
    "प्रेशरकुकर": "pressure cooker",
    "सीलिंग फैन": "ceiling fan",
    "टेबल फैन": "table fan",
    "वॉल फैन": "wall fan",
    "स्टीम आयरन": "steam iron",
    "ड्राय आयरन": "dry iron",
    "ड्राई आयरन": "dry iron",
    "वॉशिंग मशीन": "washing machine",
    "वाशिंग मशीन": "washing machine",
    "वाशिंगमशीन": "washing machine",
    "कपड़े धोने की मशीन": "washing machine",
    "माइक्रोवेव ओवन": "microwave oven",
    "एयर कंडीशनर": "ac air conditioner",
    "स्प्लिट एसी": "split ac",
    "इन्वर्टर एसी": "inverter ac",
    "बिजली का पंखा": "electric fan",
    
    # Beauty & Personal Care
    "फेस वॉश": "face wash",
    "फेसवॉश": "face wash",
    "फेस वाश": "face wash",
    "नीम फेस वॉश": "neem face wash",
    "नीम फेसवॉश": "neem face wash",
    "उबटन फेस वॉश": "ubtan face wash",
    "उबटन फेसवॉश": "ubtan face wash",
    "लेमन फेस वॉश": "lemon face wash",
    "बॉडी लोशन": "body lotion",
    "सन स्क्रीन": "sunscreen",
    "धूप वाली क्रीम": "sunscreen",
    "डार्क स्पॉट": "dark spot",
    "मैट लिपस्टिक": "matte lipstick",
    "अनियन शैम्पू": "onion shampoo",
    "प्याज शैम्पू": "onion shampoo",
    "हेयर फॉल": "hair fall",
    
    # Electronics
    "स्मार्ट वॉच": "smartwatch",
    "पावर बैंक": "powerbank",
    "पेन ड्राइव": "pendrive sandisk",
    "मेमोरी कार्ड": "memory card sandisk",
    "ब्लूटूथ स्पीकर": "bluetooth speaker",
    "फास्ट चार्जर": "fast charger",
    "बैक कवर": "case cover",
    "फोन कवर": "case cover",
    
    # Grocery & Food
    "सरसों का तेल": "mustard oil",
    "सरसों तेल": "mustard oil",
    "सोयाबीन तेल": "soybean oil",
    "मूंगफली का तेल": "groundnut oil",
    "मूंगफली तेल": "groundnut oil",
    "चक्की आटा": "chakki atta",
    "गेहूं का आटा": "wheat atta",
    "गेहूँ का आटा": "wheat atta",
    "मल्टीग्रेन आटा": "multigrain atta",
    "बासमती चावल": "basmati rice",
    "चाय पत्ती": "tea",
    "काजू बिस्कुट": "cashew cookies",
    "काजू कुकीज": "cashew cookies",
    "देसी घी": "pure ghee",
    "शुद्ध घी": "pure ghee",
    "दूध पाउडर": "milk powder",
    
    # Fashion
    "फॉर्मल जूते": "formal shoes",
    "रनिंग जूते": "running shoes",
    "स्नीकर जूते": "sneakers shoes",
    "हैंडलूम कुर्ता": "handloom kurta",
    "सिल्क साड़ी": "silk saree",
    "सिल्क साड़ी": "silk saree",
    "कॉटन साड़ी": "cotton saree",
    "कॉटन साड़ी": "cotton saree",
    "स्लिंग बैग": "sling bag",
    "टोट बैग": "tote bag",
    "शोल्डर बैग": "shoulder bag",
    
    # Brands (multi-word)
    "एप्पल आईफोन": "apple iphone",
    "ऐप्पल आईफोन": "apple iphone",
    "रियल मी": "realme",
    "वन प्लस": "oneplus",
    "एलन सोली": "allen solly",
    "एलन सॉली": "allen solly",
    "फैब इंडिया": "fabindia",
    "फायर बोल्ट": "fire-boltt",
    "मामा अर्थ": "mamaearth",
    "वाइल्ड स्टोन": "wild stone",
    "बेला वीटा": "bella vita",
    
    # Price & Quality intents
    "कम दाम": "cheap budget",
    "कम कीमत": "cheap budget",
    "कम रेट": "cheap budget",
    "कम पैसे": "cheap budget",
    "सस्ता वाला": "cheap budget",
    "सस्ती वाली": "cheap budget",
    "सस्ते में": "cheap budget",
    "सबसे सस्ता": "cheap low price",
    "सबसे सस्ते": "cheap low price",
    "सबसे सस्ती": "cheap low price",
    "अच्छा वाला": "best quality",
    "बढ़िया वाला": "best quality",
    "सफेद चावल": "white rice",
    "कर्व्ड डिस्प्ले": "curved amoled",
    "कर्व्ड एमोलेड": "curved amoled",
}

# Single word mappings (Devanagari & Hinglish -> English catalog concepts)
WORD_MAPPINGS: dict[str, str] = {
    # 38 Catalogue Brands (Devanagari)
    "सैमसंग": "samsung",
    "रेडमी": "redmi",
    "रियलमी": "realme",
    "वीवो": "vivo",
    "विवो": "vivo",
    "वनप्लस": "oneplus",
    "एप्पल": "apple",
    "ऐप्पल": "apple",
    "आईफोन": "iphone",
    "आइफोन": "iphone",
    "बाटा": "bata",
    "प्यूमा": "puma",
    "पुमा": "puma",
    "लेविस": "levis",
    "लिवाइस": "levis",
    "लेवीस": "levis",
    "फैबइंडिया": "fabindia",
    "बीबा": "biba",
    "आशीर्वाद": "aashirvaad",
    "आशिरवाद": "aashirvaad",
    "पतंजलि": "patanjali",
    "पतन्जलि": "patanjali",
    "टाटा": "tata",
    "ब्रिटानिया": "britannia",
    "ब्रिटैनिया": "britannia",
    "डाबर": "dabur",
    "अमूल": "amul",
    "अमुल": "amul",
    "बोट": "boat",
    "सोनी": "sony",
    "बोल्ट": "boult",
    "जेबीएल": "jbl",
    "नॉइज़": "noise",
    "नॉइज": "noise",
    "फायरबोल्ट": "fire-boltt",
    "शाओमी": "xiaomi",
    "श्याओमी": "xiaomi",
    "अम्ब्रैन": "ambrane",
    "एम्ब्रेन": "ambrane",
    "सैनडिस्क": "sandisk",
    "सैंडिस्क": "sandisk",
    "हिमालया": "himalaya",
    "हिमालय": "himalaya",
    "मामाअर्थ": "mamaearth",
    "लक्मे": "lakme",
    "लैक्मे": "lakme",
    "निविया": "nivea",
    "निवेया": "nivea",
    "डव": "dove",
    "मेबेलिन": "maybelline",
    "मेबिलिन": "maybelline",
    "प्रेस्टीज": "prestige",
    "बजाज": "bajaj",
    "फिलिप्स": "philips",
    "फीलिप्स": "philips",
    "हैवेल्स": "havells",
    "हैवल्स": "havells",
    "एलजी": "lg",
    "फॉग्": "fogg",
    "फॉग": "fogg",
    "एंगेज": "engage",

    # Mobiles & Accessories
    "फोन": "phone",
    "फ़ोन": "phone",
    "मोबाइल": "mobile",
    "मोबाईल": "mobile",
    "स्मार्टफोन": "phone",
    "चार्जर": "charger",
    "एडाप्टर": "adapter",
    "अडैप्टर": "adapter",
    "कवर": "case cover",
    "केस": "case",

    # Fashion
    "जूता": "shoes",
    "जूते": "shoes",
    "जूतों": "shoes",
    "शूज": "shoes",
    "स्नीकर": "sneakers",
    "स्नीकर्स": "sneakers",
    "सैंडल": "sandals",
    "चप्पल": "chappals",
    "फ्लैट्स": "flats",
    "टीशर्ट": "t-shirt",
    "टी-शर्ट": "t-shirt",
    "पोलो": "polo",
    "जींस": "jeans",
    "जीन्स": "jeans",
    "डेनिम": "denim",
    "पैंट": "jeans",
    "कुर्ता": "kurta",
    "कुर्ती": "kurta",
    "अनारकली": "anarkali",
    "साड़ी": "saree",
    "साड़ियां": "saree",
    "साड़ी": "saree",
    "बैग": "bag",
    "हैंडबैग": "handbag",
    "पर्स": "handbag",
    "थैला": "bag",
    "बैकपैक": "backpack",
    "टोट": "tote",
    "स्लिंग": "sling",

    # Food & Health
    "आटा": "atta",
    "गेहूं": "wheat",
    "गेहूँ": "wheat",
    "चक्की": "chakki",
    "चावल": "rice",
    "बासमती": "basmati",
    "पोहा": "poha",
    "तेल": "oil",
    "सरसों": "mustard",
    "रिफाइंड": "refined",
    "सोयाबीन": "soybean",
    "मूंगफली": "groundnut",
    "चाय": "tea",
    "चायपत्ती": "tea",
    "कॉफी": "coffee",
    "बिस्कुट": "biscuits",
    "बिस्किट": "biscuits",
    "कुकीज": "cookies",
    "कुकी": "cookies",
    "नमकीन": "snacks",
    "स्नैक्स": "snacks",
    "मक्खन": "butter",
    "बटर": "butter",
    "दूध": "milk",
    "मिल्क": "milk",
    "दही": "curd",
    "छाछ": "buttermilk",
    "लस्सी": "lassi",
    "घी": "ghee",
    "जूस": "juice",
    "आंवला": "amla",
    "एलोवेरा": "aloe vera",
    "हॉर्लिक्स": "horlicks",
    "बॉर्नविटा": "bournvita",
    "ग्लूकोज": "glucose",
    "विटामिन": "vitamins",
    "मल्टीविटामिन": "multivitamin",
    "च्यवनप्राश": "chyawanprash",
    "हाजमोला": "hajmola",
    "शहद": "honey",
    "गिलोय": "giloy",
    "अश्वगंधा": "ashwagandha",
    "शिलाजीत": "shilajit",

    # Electronics
    "इयरबड्स": "earbuds",
    "ईयरबड्स": "earbuds",
    "बड्स": "earbuds",
    "एयरपॉड": "earbuds",
    "एयरपॉड्स": "earbuds",
    "इयरफोन": "earphones",
    "ईयरफोन": "earphones",
    "हेडफोन": "headphones",
    "हेडफ़ोन": "headphones",
    "नेकबैंड": "neckband",
    "घड़ी": "smartwatch",
    "घड़ी": "smartwatch",
    "स्मार्टवॉच": "smartwatch",
    "स्पीकर": "speaker",
    "साउंडबार": "speaker",
    "पावरबैंक": "powerbank",
    "पेनड्राइव": "pendrive sandisk",
    "मेमोरी": "memory card sandisk",
    "एसएसडी": "ssd",
    "स्टोरेज": "storage",

    # Beauty
    "फेसवॉश": "face wash",
    "नीम": "neem",
    "उबटन": "ubtan",
    "लेमन": "lemon",
    "मॉइस्चराइजर": "moisturizer",
    "मॉइश्चराइजर": "moisturizer",
    "लोशन": "lotion",
    "क्रीम": "cream moisturizer",
    "शैम्पू": "shampoo",
    "शैंपू": "shampoo",
    "शम्पू": "shampoo",
    "लिपस्टिक": "lipstick",
    "लिपिस्टिक": "lipstick",
    "परफ्यूम": "perfume",
    "इत्र": "perfume",
    "सेंट": "perfume",
    "डिओड्रेंट": "deodorant",
    "डियो": "deodorant",
    "सनस्क्रीन": "sunscreen",
    "धूप": "sunscreen",

    # Appliances
    "मिक्सर": "mixer grinder",
    "मिक्सी": "mixer grinder",
    "ग्राइंडर": "mixer grinder",
    "कुकर": "pressure cooker",
    "पंखा": "fan",
    "पंखे": "fan",
    "फैन": "fan",
    "इस्त्री": "iron",
    "प्रेस": "iron",
    "आयरन": "iron",
    "माइक्रोवेव": "microwave",
    "ओवन": "microwave",
    "वॉशिंग": "washing machine",
    "वाशिंग": "washing machine",
    "मशीन": "machine",
    "एसी": "ac",

    # Adjectives & Intents
    "सस्ता": "cheap", "सस्ते": "cheap", "सस्ती": "cheap",
    "बजट": "budget", "किफायती": "budget",
    "अच्छा": "best", "अच्छी": "best", "अच्छे": "best", "बढ़िया": "best",
    "नया": "new", "नई": "new", "नये": "new",

    # Hinglish & transliterations
    "sasta": "cheap", "saste": "cheap", "sasti": "cheap",
    "atta": "atta", "aata": "atta", "dal": "dal", "daal": "dal",
    "chai": "tea", "chaye": "tea", "chawal": "rice",
    "juta": "shoes", "joote": "shoes", "joota": "shoes",
    "chappal": "sandals", "kapde": "clothing", "kapda": "cloth",
    "kurti": "kurta", "bartan": "cookware", "kadai": "kadhai",
    "doodh": "milk", "makkhan": "butter", "dahi": "curd",
    "cheeni": "sugar", "namak": "salt", "mirch": "chilli",
    "haldi": "turmeric", "tel": "oil", "sabun": "soap",
    "ghadi": "smartwatch", "gadi": "smartwatch",
    "masala": "spices", "mobail": "mobile", "fone": "phone",
    "bluetoth": "bluetooth", "blutooth": "bluetooth",
}

# Number words mapping in Hinglish and Hindi
NUMBER_UNITS: dict[str, int] = {
    "hajar": 1000,
    "hazar": 1000,
    "हजार": 1000,
    "हज़ार": 1000,
    "हज़ार": 1000,
    "sau": 100,
    "सौ": 100,
    "lakh": 100000,
    "lac": 100000,
    "लाख": 100000,
    "k": 1000,
}

HINDI_NUMBERS: dict[str, int] = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "pandrah": 15, "bees": 20, "pachis": 25, "tees": 30, "chalis": 40, "pachas": 50,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50,
    "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}

PRICE_SKIP_TOKENS: Set[str] = {
    "cheap", "sasta", "saste", "sasti", "budget", "low", "price",
    "hajar", "hazar", "हजार", "हज़ार", "हज़ार", "sau", "सौ", "lakh", "लाख", "k",
    "under", "below", "tak", "kam", "se", "andar", "तक", "कम", "से", "अंदर"
}


def normalize_hinglish_query(query: str) -> dict[str, Any]:
    """Clean, transliterate, and normalize a Hindi/Hinglish query with brand protection."""
    raw = (query or "").strip()
    if not raw:
        return {
            "original": "",
            "rewritten": "",
            "tokens": [],
            "brand_preserved": None,
            "extracted_price": None,
            "low_cost_intent": False,
        }

    # Step 1: Remove punctuation including Hindi full-stop '।' (purna viram '॥') and English symbols
    cleaned = re.sub(r"[\.\,\!\?\;\:\'\"\\\/\|\`\~\@\#\$\%\^\&\*\(\)\_\+\=\[\]\{\}\<\>।॥]", " ", raw)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Step 2: Detect budget / low-cost intent
    budget_terms = [
        "sasta", "saste", "sasti", "kam daam", "kam keemat", "kam kimat", "kam rate",
        "budget", "cheap", "low price", "सस्ता", "सस्ते", "सस्ती", "कम दाम", "कम कीमत", "कम रेट", "कम पैसे"
    ]
    low_cost_intent = any(bt in cleaned for bt in budget_terms)

    # Step 3: Extract price constraints (e.g. "10 hajar", "5000 se kam", "10 हजार तक", "under 15000")
    extracted_price: Optional[float] = None
    extracted_number_str: Optional[str] = None

    # Pattern for "N hajar" or "N thousand"
    price_pattern = re.search(
        r"(\d+|ek|do|teen|chaar|char|paanch|panch|chhe|saat|aath|nau|das|bees|pachas|एक|दो|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस|बीस|पचास)\s*(hajar|hazar|हजार|हज़ार|हज़ार|sau|सौ|k|lakh|लाख)\b",
        cleaned
    )
    if price_pattern:
        num_part = price_pattern.group(1)
        unit_part = price_pattern.group(2)
        base_num = int(num_part) if num_part.isdigit() else HINDI_NUMBERS.get(num_part, 1)
        mult = NUMBER_UNITS.get(unit_part, 1000)
        extracted_price = float(base_num * mult)
        extracted_number_str = num_part
    else:
        # Check direct numeric patterns like "5000 se kam" or "5000 tak" or "under 5000"
        num_match = re.search(r"\b(\d{3,6})\s*(se kam|tak|ke andar|under|below|से कम|तक|के अंदर)\b", cleaned)
        if not num_match:
            num_match = re.search(r"\b(under|below|कम)\s*(\d{3,6})\b", cleaned)
            if num_match:
                extracted_price = float(num_match.group(2))
                extracted_number_str = num_match.group(2)
        else:
            extracted_price = float(num_match.group(1))
            extracted_number_str = num_match.group(1)

    # Step 4: Multi-word phrase mapping (Devanagari & Hinglish)
    rewritten = cleaned
    for phrase, target in sorted(PHRASE_MAPPINGS.items(), key=lambda x: len(x[0]), reverse=True):
        if phrase in rewritten:
            rewritten = rewritten.replace(phrase, f" {target} ")

    rewritten = re.sub(r"\s+", " ", rewritten).strip()

    # Step 5: Word-by-word replacement with Brand Protection
    raw_tokens = rewritten.split()
    translated_tokens: List[str] = []
    preserved_brand: Optional[str] = None

    for token in raw_tokens:
        # Check if already a protected brand in English
        if token in PROTECTED_BRANDS:
            preserved_brand = token
            translated_tokens.append(token)
            continue

        # Check WORD_MAPPINGS
        if token in WORD_MAPPINGS:
            mapped = WORD_MAPPINGS[token]
            translated_tokens.extend(mapped.split())
        else:
            translated_tokens.append(token)

    # Step 6: Filter out conversational stopwords and price-only artifacts
    final_tokens: List[str] = []
    for token in translated_tokens:
        if token in HINDI_STOPWORDS:
            continue
        if token in PRICE_SKIP_TOKENS:
            continue
        if extracted_number_str and token == extracted_number_str:
            continue
        if token.isdigit() and extracted_price and float(token) == extracted_price:
            continue
        if len(token) <= 1:
            continue
        final_tokens.append(token)

    # Step 7: Check preserved brand after word mapping
    if not preserved_brand:
        for b in sorted(PROTECTED_BRANDS, key=len, reverse=True):
            if b in final_tokens or b in " ".join(final_tokens):
                preserved_brand = b
                break

    final_rewritten = " ".join(final_tokens)

    return {
        "original": raw,
        "rewritten": final_rewritten,
        "tokens": final_tokens,
        "brand_preserved": preserved_brand,
        "extracted_price": extracted_price,
        "low_cost_intent": low_cost_intent,
    }
