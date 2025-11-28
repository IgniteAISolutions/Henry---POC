"""
Configuration, constants, and category-specific rules
"""

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_RETRIES = 3
OPENAI_TIMEOUT = 120

# Categories
ALLOWED_CATEGORIES = {
    "Bakeware, Cookware",
    "Dining, Drink, Living",
    "Electricals",
    "Food Prep & Tools",
    "Knives, Cutlery",
    "Clothing",
    "Seasonal"
}

# Category-specific lifestyle:technical ratios
CATEGORY_MATRIX = {
    "Clothing": {"lifestyle": 100, "technical": 0},
    "Electricals": {"lifestyle": 0, "technical": 100},
    "Bakeware, Cookware": {"lifestyle": 50, "technical": 50},
    "Dining, Drink, Living": {"lifestyle": 80, "technical": 20},
    "Knives, Cutlery": {"lifestyle": 30, "technical": 70},
    "Food Prep & Tools": {"lifestyle": 60, "technical": 40},
    "Seasonal": {"lifestyle": 50, "technical": 50}
}

# Spec allow-lists per category
ALLOWED_SPECS = {
    "Knives, Cutlery": {"material", "bladeLength", "dimensions", "weight", "origin", "guarantee", "care"},
    "Electricals": {"capacity", "dimensions", "weight", "powerW", "programs", "origin", "guarantee", "care"},
    "Dining, Drink, Living": {"material", "capacity", "dimensions", "weight", "origin", "guarantee", "care"},
    "Bakeware, Cookware": {"material", "dimensions", "weight", "capacity", "origin", "guarantee", "care"},
    "Food Prep & Tools": {"material", "dimensions", "weight", "origin", "guarantee", "care"},
    "Clothing": {"material", "dimensions", "weight", "origin", "care"},
    "Seasonal": {"material", "dimensions", "weight", "capacity", "origin", "guarantee", "care"},
    "General": {"material", "dimensions", "weight", "capacity", "origin", "guarantee", "care"}
}

# Forbidden phrases
FORBIDDEN_PHRASES = [
    "Harts of Stur",
    "Since 1919",
    "Since 1990",
    "Dorset",
    "family-run",
    "family run",
    "imported from"
]

# Banned SEO keywords
BANNED_SEO_KEYWORDS = {
    "shop", "shops", "shopping",
    "buy", "order", "orders", "price", "prices", "sale"
}

# System prompt
SYSTEM_PROMPT = """Act like a senior UK e-commerce copy chief and prompt engineer. You specialise in turning product data into warm, trustworthy, benefit-led copy that helps shoppers choose with confidence. Produce compliant, high-quality HTML only.
OBJECTIVE
Return valid JSON with exactly two keys (no markdown, no comments):
{ "short_html": "<p>…</p>", "long_html": "<p>…</p><p>…</p>…" }
TONE & PRINCIPLES
- UK English only.
- Warm, knowledgeable, practical; benefit-first; transparent and reassuring.
- The business is a retailer/redistributor, not a manufacturer.
- Do NOT mention retailer location, "Dorset", "family-run", "Since 1919", or any in-house manufacturing.
- Truthful and product-data-grounded. Never invent specifications or claims.
- No em dashes.
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
