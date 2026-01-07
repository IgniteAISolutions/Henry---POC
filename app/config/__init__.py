"""
EarthFare Configuration Package
"""
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

__all__ = [
    "SUPPLIER_CONFIGS",
    "SOURCE_WEIGHTS",
    "FALLBACK_SEARCH_URLS",
    "BRAND_WEBSITES",
    "get_supplier_config",
    "get_all_supplier_configs",
    "get_brand_website",
    "slugify"
]
