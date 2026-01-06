"""
Configuration, constants, and category-specific rules
"""

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_RETRIES = 3
OPENAI_TIMEOUT = 120

# Categories - EarthFare Natural Grocery
ALLOWED_CATEGORIES = {
    "Store Cupboard",
    "Fresh Produce",
    "Dairy & Alternatives",
    "Bakery",
    "Beverages",
    "Snacks & Treats",
    "Health & Beauty",
    "Household & Eco",
    "Supplements & Wellness",
    "Frozen",
    "Chilled"
}

# Category-specific lifestyle:technical ratios
CATEGORY_MATRIX = {
    "Store Cupboard": {"lifestyle": 70, "technical": 30},
    "Fresh Produce": {"lifestyle": 80, "technical": 20},
    "Dairy & Alternatives": {"lifestyle": 60, "technical": 40},
    "Bakery": {"lifestyle": 80, "technical": 20},
    "Beverages": {"lifestyle": 70, "technical": 30},
    "Snacks & Treats": {"lifestyle": 80, "technical": 20},
    "Health & Beauty": {"lifestyle": 50, "technical": 50},
    "Household & Eco": {"lifestyle": 40, "technical": 60},
    "Supplements & Wellness": {"lifestyle": 30, "technical": 70},
    "Frozen": {"lifestyle": 60, "technical": 40},
    "Chilled": {"lifestyle": 70, "technical": 30},
    "General": {"lifestyle": 60, "technical": 40}
}

# Spec allow-lists per category - EarthFare focus on dietary, sourcing, certifications
ALLOWED_SPECS = {
    "Store Cupboard": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Fresh Produce": {"weight", "origin", "dietary", "certifications", "producer", "region"},
    "Dairy & Alternatives": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Bakery": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Beverages": {"volume", "origin", "dietary", "certifications", "ingredients", "servings"},
    "Snacks & Treats": {"weight", "origin", "dietary", "certifications", "ingredients", "servings"},
    "Health & Beauty": {"volume", "weight", "origin", "certifications", "ingredients", "usage"},
    "Household & Eco": {"volume", "weight", "origin", "certifications", "ingredients", "usage"},
    "Supplements & Wellness": {"weight", "origin", "dietary", "certifications", "ingredients", "dosage", "servings"},
    "Frozen": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Chilled": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "General": {"weight", "origin", "dietary", "certifications", "ingredients"}
}

# Forbidden phrases - EarthFare specific
FORBIDDEN_PHRASES = [
    "EarthFare",           # Brand name (use sparingly, not in product copy)
    "save the planet",     # Guilt-based messaging
    "you should",          # Preachy language
    "you must",            # Preachy language
    "conventional",        # Avoid criticising conventional alternatives
    "supermarket",         # Competitor reference
    "mass-produced",       # Negative competitor language
    "Sainsbury",           # Competitor
    "Marks and Spencer",   # Competitor
    "Tesco",               # Competitor
    "imported from"        # Vague sourcing
]

# Banned SEO keywords
BANNED_SEO_KEYWORDS = {
    "shop", "shops", "shopping",
    "buy", "order", "orders", "price", "prices", "sale",
    "cheap", "discount", "bargain"
}

# System prompt (brief version for config, full version in brand_voice.py)
SYSTEM_PROMPT = """You are a UK e-commerce copy specialist writing for Earthfare, an eco supermarket in Glastonbury.
OBJECTIVE
Return valid JSON with Shopify-compatible fields:
{ "title": "...", "body_html": "...", "short_description": "...", "meta_description": "...", "dietary_preferences": [...], "brand": "..." }
TONE & PRINCIPLES
- UK English only. Short, punchy sentences.
- Warm, conversational, joyfully sustainable. Use "we" and "you" language.
- Invitational, never preachy. Ethical choices as delightful discoveries.
- Highlight: thoughtfully sourced, small local producers, artisan, planet friendly.
- Truthful and product-data-grounded. Never invent claims.
"""

# SEO Configuration
SEO_META_MIN_LENGTH = 150
SEO_META_MAX_LENGTH = 160
SEO_META_IDEAL_LENGTH = 155

# CSV Export Configuration
CSV_BOM = "\ufeff"
CSV_DEFAULT_HEADERS = [
    "sku", "barcode", "name",
    "shortDescription", "longDescription", "metaDescription",
    "weightGrams", "weightHuman"
]

# Image Processing
MAX_IMAGE_SIZE_MB = 10
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

# URL Scraping
URL_SCRAPE_TIMEOUT = 30
URL_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Text Processing
TEXT_MIN_LENGTH = 10
TEXT_MAX_LENGTH = 10000
