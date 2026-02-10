"""
Configuration, constants, and category-specific rules
"""

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_RETRIES = 3
OPENAI_TIMEOUT = 120

# Categories - EarthFare Natural Grocery
# 9 Main categories aligned with Shopify/Vector departments
ALLOWED_CATEGORIES = {
    "Groceries",
    "Fresh",
    "Drinks",
    "Frozen",
    "Household and Non-Food",
    "Body Care",
    "Health",
    "Promo and Seasonal",
    "Earthfare Kitchen",
}

# Subcategory mapping - main category to list of subcategories
CATEGORY_SUBCATEGORIES = {
    "Groceries": [
        "Ambient Grocery",
        "Baking & Home Cooking",
        "Breakfast & Cereals",
        "Condiments & Sauces",
        "Cooking Oils & Vinegars",
        "Herbs, Spices & Seasonings",
        "Jams, Honey & Spreads",
        "Pasta, Rice & Grains",
        "Snacks & Treats",
        "Tinned & Jarred Foods",
        "World Foods",
    ],
    "Fresh": [
        "Bakery",
        "Cheese",
        "Chilled Deli",
        "Dairy & Alternatives",
        "Fresh Fruit & Veg",
        "Meat & Fish Alternatives",
        "Ready Meals & Fresh Pasta",
    ],
    "Drinks": [
        "Coffee & Tea",
        "Fruit Juices & Smoothies",
        "Soft Drinks & Cordials",
        "Water",
        "Wine, Beer & Spirits",
    ],
    "Frozen": [
        "Frozen Desserts",
        "Frozen Fruit & Veg",
        "Frozen Meals & Pizza",
        "Frozen Meat Alternatives",
        "Ice Cream & Lollies",
    ],
    "Household and Non-Food": [
        "Cleaning Products",
        "Kitchen & Household",
        "Laundry",
        "Pet Food & Care",
        "Stationery & Gifts",
    ],
    "Body Care": [
        "Baby & Child",
        "Bath & Shower",
        "Dental Care",
        "Deodorants",
        "Face & Skincare",
        "Hair Care",
        "Hand & Body",
        "Men's Grooming",
        "Period Care",
        "Sun Care",
    ],
    "Health": [
        "First Aid & Medical",
        "Supplements & Vitamins",
        "Wellness & Natural Remedies",
    ],
    "Promo and Seasonal": [
        "Christmas",
        "Easter",
        "Gift Sets",
        "Seasonal Specials",
    ],
    "Earthfare Kitchen": [
        "Hot Food",
        "Sandwiches & Wraps",
        "Salads & Sides",
        "Cakes & Pastries",
    ],
}

# Category-specific lifestyle:technical ratios
CATEGORY_MATRIX = {
    "Groceries": {"lifestyle": 70, "technical": 30},
    "Fresh": {"lifestyle": 80, "technical": 20},
    "Drinks": {"lifestyle": 70, "technical": 30},
    "Frozen": {"lifestyle": 60, "technical": 40},
    "Household and Non-Food": {"lifestyle": 40, "technical": 60},
    "Body Care": {"lifestyle": 50, "technical": 50},
    "Health": {"lifestyle": 30, "technical": 70},
    "Promo and Seasonal": {"lifestyle": 80, "technical": 20},
    "Earthfare Kitchen": {"lifestyle": 85, "technical": 15},
    "General": {"lifestyle": 60, "technical": 40}  # Fallback
}

# Spec allow-lists per category - EarthFare focus on dietary, sourcing, certifications
ALLOWED_SPECS = {
    "Groceries": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Fresh": {"weight", "origin", "dietary", "certifications", "ingredients", "producer", "storage"},
    "Drinks": {"volume", "origin", "dietary", "certifications", "ingredients", "servings"},
    "Frozen": {"weight", "origin", "dietary", "certifications", "ingredients", "storage"},
    "Household and Non-Food": {"volume", "weight", "origin", "certifications", "ingredients", "usage"},
    "Body Care": {"volume", "weight", "origin", "certifications", "ingredients", "usage"},
    "Health": {"weight", "origin", "dietary", "certifications", "ingredients", "dosage", "servings"},
    "Promo and Seasonal": {"weight", "origin", "dietary", "certifications", "ingredients"},
    "Earthfare Kitchen": {"weight", "origin", "dietary", "certifications", "ingredients", "allergens"},
    "General": {"weight", "origin", "dietary", "certifications", "ingredients"}  # Fallback
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
