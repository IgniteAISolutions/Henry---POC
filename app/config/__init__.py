"""
EarthFare Configuration Package
"""
import os

from .suppliers import (
    SUPPLIER_CONFIGS,
    SOURCE_WEIGHTS,
    FALLBACK_SEARCH_URLS,
    BRAND_WEBSITES,
    get_supplier_config,
    get_all_supplier_configs,
    get_brand_website,
    slugify
)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_RETRIES = 3
OPENAI_TIMEOUT = 120

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

# EarthFare grocery categories - 9 Main categories aligned with Shopify/Vector departments
ALLOWED_CATEGORIES = [
    "Groceries",
    "Fresh",
    "Drinks",
    "Frozen",
    "Household and Non-Food",
    "Body Care",
    "Health",
    "Promo and Seasonal",
    "Earthfare Kitchen",
]

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

# Forbidden phrases - EarthFare specific
FORBIDDEN_PHRASES = [
    "EarthFare",
    "save the planet",
    "you should",
    "you must",
    "conventional",
    "supermarket",
    "mass-produced",
    "Sainsbury",
    "Marks and Spencer",
    "Tesco",
    "imported from"
]

# SEO Configuration
SEO_META_MIN_LENGTH = 150
SEO_META_MAX_LENGTH = 160
BANNED_SEO_KEYWORDS = {
    "shop", "shops", "shopping",
    "buy", "order", "orders", "price", "prices", "sale",
    "cheap", "discount", "bargain"
}

# CSV Export Configuration
CSV_BOM = "\ufeff"
CSV_DEFAULT_HEADERS = [
    "sku", "barcode", "name",
    "shortDescription", "longDescription", "metaDescription",
    "weightGrams", "weightHuman"
]

# Text Processing
TEXT_MIN_LENGTH = 10
TEXT_MAX_LENGTH = 10000

__all__ = [
    "SUPPLIER_CONFIGS",
    "SOURCE_WEIGHTS",
    "FALLBACK_SEARCH_URLS",
    "BRAND_WEBSITES",
    "get_supplier_config",
    "get_all_supplier_configs",
    "get_brand_website",
    "slugify",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_MAX_RETRIES",
    "OPENAI_TIMEOUT",
    "ALLOWED_CATEGORIES",
    "ALLOWED_SPECS",
    "CATEGORY_SUBCATEGORIES",
    "CATEGORY_MATRIX",
    "FORBIDDEN_PHRASES",
    "SEO_META_MIN_LENGTH",
    "SEO_META_MAX_LENGTH",
    "BANNED_SEO_KEYWORDS",
    "CSV_BOM",
    "CSV_DEFAULT_HEADERS",
    "TEXT_MIN_LENGTH",
    "TEXT_MAX_LENGTH",
]
