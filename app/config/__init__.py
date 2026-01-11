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
    "OPENAI_MAX_RETRIES",
    "OPENAI_TIMEOUT",
    "ALLOWED_CATEGORIES",
    "ALLOWED_SPECS",
]
