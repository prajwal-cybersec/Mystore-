"""Hinglish-aware query understanding and normalizer module.

Normalizes text, applies a curated Hinglish->English synonym / transliteration dictionary,
protects known Indian and global brand names from unwanted rewriting, and extracts
numeric price intents (e.g. "8 hajar" -> 8000).
"""

from __future__ import annotations

import re
from typing import Any

# Brand protection set (must never be mangled)
PROTECTED_BRANDS = {
    "samsung", "oneplus", "realme", "xiaomi", "boat", "jbl", "apple", "lenovo", "hp", "sony",
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
    "lifebuoy", "head & shoulders", "tresemme", "parachute", "gillette", "colgate", "sensodyne"
}

# Hinglish phrases -> English search terms
PHRASE_MAPPINGS = {
    "kam keemat": "cheap low price",
    "kam daam": "cheap budget",
    "kam daam me": "cheap budget",
    "sasta wala": "cheap",
    "saste me": "cheap",
    "accha wala": "best quality",
    "laal rang": "red color",
    "neela rang": "blue color",
    "kaala rang": "black color",
    "safed rang": "white color",
    "safed chawal": "white rice",
    "peeli dal": "yellow dal",
    "garam masala": "garam masala",
    "chai patti": "tea",
    "chaye patti": "tea",
    "nahane ka sabun": "bathing soap",
    "tel ki botal": "oil bottle",
    "mitha tel": "edible oil",
    "sarso ka tel": "mustard oil",
    "sarson ka tel": "mustard oil",
    "khana pakane ka bartan": "cookware",
    "kaano ka headphone": "earphones headphones",
    "doodh powder": "milk powder",
    "daant ka paste": "toothpaste",
    "paani ki botal": "water bottle",
}

# Hinglish single words -> English / Standard equivalents
WORD_MAPPINGS = {
    "sasta": "cheap",
    "saste": "cheap",
    "sasti": "cheap",
    "atta": "flour",
    "aata": "flour",
    "chawal": "rice",
    "juta": "shoes",
    "joote": "shoes",
    "joota": "shoes",
    "chappal": "sandals",
    "kapde": "clothing",
    "kapda": "cloth",
    "kurti": "kurta",
    "bartan": "cookware",
    "kadai": "kadhai",
    "doodh": "milk",
    "makkhan": "butter",
    "dahi": "curd",
    "cheeni": "sugar",
    "shakkar": "sugar",
    "namak": "salt",
    "mirch": "chilli",
    "mirchi": "chilli",
    "haldi": "turmeric",
    "dhaniya": "coriander",
    "tel": "oil",
    "sabun": "soap",
    "gadi": "watch",
    "ghadi": "watch",
    "paani": "water",
    "bijli": "electric",
    "towel": "towel",
    "tauliya": "towel",
    "chammach": "spoon",
    "thali": "plate",
    "papad": "papad",
    "achaar": "pickle",
    "achar": "pickle",
    "masala": "spices",
    "shampoo": "shampoo",
    "phone": "phone",
    "earphone": "earphones",
    "earphones": "earphones",
    "bluetoth": "bluetooth",
    "blutooth": "bluetooth",
    "mobail": "mobile",
    "fone": "phone",
    # Common Devanagari words translated to English catalog keywords
    "दाल": "dal toor",
    "तूर": "toor",
    "अरहर": "arhar toor",
    "आटा": "atta flour",
    "चावल": "rice",
    "चीनी": "sugar",
    "नमक": "salt",
    "हल्दी": "turmeric haldi",
    "तेल": "oil",
    "साबुन": "soap",
    "दूध": "milk",
    "जूता": "shoes",
    "जूते": "shoes",
    "कपड़े": "clothing",
    "कुर्ता": "kurta",
    "कुर्ती": "kurta",
    "चाय": "tea",
    "कॉफी": "coffee",
    "मसाला": "masala spices",
    "सस्ता": "cheap",
    "सस्ते": "cheap",
    "इयरफोन": "earphones",
    "हेडफोन": "headphones",
    "मोबाइल": "mobile phone",
    "फोन": "phone",
    "घड़ी": "watch",
}

# Number words in Hinglish
NUMBER_UNITS = {
    "hajar": 1000,
    "hazar": 1000,
    "sau": 100,
    "so": 100,
    "lakh": 100000,
    "lac": 100000,
    "k": 1000,
}

HINDI_NUMBERS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "pandrah": 15, "bees": 20, "pachis": 25, "tees": 30, "chalis": 40, "pachas": 50,
}


def normalize_hinglish_query(query: str) -> dict[str, Any]:
    """Clean, transliterate, and normalize a query string with brand protection."""
    raw = (query or "").strip()
    if not raw:
        return {"original": "", "rewritten": "", "brand_preserved": None, "extracted_price": None}

    # Remove punctuation including Hindi full-stop '।' (purna viram '॥') and English periods/symbols
    cleaned = re.sub(r"[\.\,\!\?\;\:\'\"\\\/\|\`\~\@\#\$\%\^\&\*\(\)\_\+\=\[\]\{\}\<\>।॥]", " ", raw)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Detect protected brands
    preserved_brand = None
    for brand in sorted(PROTECTED_BRANDS, key=len, reverse=True):
        # Match as whole word/phrase
        pattern = r"\b" + re.escape(brand) + r"\b"
        if re.search(pattern, cleaned):
            preserved_brand = brand
            break

    # Extract price intents like "8 hajar", "under 10k", "500 se kam"
    extracted_price = None
    # Check "N hajar" or "word hajar"
    price_pattern = re.search(r"(\d+|ek|do|teen|chaar|char|paanch|panch|chhe|saat|aath|nau|das|bees|pachas)\s*(hajar|hazar|k|lakh|lac)\b", cleaned)
    if price_pattern:
        num_part = price_pattern.group(1)
        unit_part = price_pattern.group(2)
        base_num = int(num_part) if num_part.isdigit() else HINDI_NUMBERS.get(num_part, 1)
        mult = NUMBER_UNITS.get(unit_part, 1000)
        extracted_price = base_num * mult

    # Replace multi-word phrases first
    rewritten = cleaned
    for phrase, target in PHRASE_MAPPINGS.items():
        if phrase in rewritten:
            rewritten = re.sub(r"\b" + re.escape(phrase) + r"\b", target, rewritten)

    # Word-by-word replacement while keeping brand safe
    tokens = rewritten.split()
    output_tokens = []
    for token in tokens:
        if preserved_brand and token in preserved_brand.split():
            output_tokens.append(token)
            continue
        mapped = WORD_MAPPINGS.get(token, token)
        output_tokens.append(mapped)

    final_rewritten = " ".join(output_tokens)
    final_rewritten = re.sub(r"\s+", " ", final_rewritten).strip()

    return {
        "original": raw,
        "rewritten": final_rewritten,
        "brand_preserved": preserved_brand,
        "extracted_price": extracted_price,
    }

