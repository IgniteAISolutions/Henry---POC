"""
Shared utilities for Universal Product Automation
"""
from .text_processing import (
    sanitize_html_p,
    strip_brand_taglines,
    strip_provenance,
    normalize_paragraphs,
    sanitize_csv_content,
    clamp,
    first_sentence,
    format_dimensions,
    format_capacity,
    categorize_product,
    extract_sku_patterns,
    extract_specifications,
    generate_product_id,
    validate_product_data,
)

__all__ = [
    "sanitize_html_p",
    "strip_brand_taglines",
    "strip_provenance",
    "normalize_paragraphs",
    "sanitize_csv_content",
    "clamp",
    "first_sentence",
    "format_dimensions",
    "format_capacity",
    "categorize_product",
    "extract_sku_patterns",
    "extract_specifications",
    "generate_product_id",
    "validate_product_data",
]
