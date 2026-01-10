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

# EarthFare grocery categories
ALLOWED_CATEGORIES = [
    "Store Cupboard",
    "Fresh Produce",
    "Dairy & Alternatives",
    "Bakery",
    "Frozen",
    "Drinks",
    "Health & Beauty",
    "Household",
    "Baby & Kids",
    "Pet Care",
]

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
    "ALLOWED_CATEGORIES",
]
