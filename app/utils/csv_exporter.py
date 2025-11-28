"""
CSV Export with BOM, sanitization, and dynamic columns
Exact port from Supabase TypeScript
"""
import csv
import io
from typing import List, Dict, Set, Any
from .sanitizers import strip_forbidden_phrases, normalize_paragraphs, enforce_title_in_first_sentence
from ..config import CSV_BOM, CSV_DEFAULT_HEADERS


def generate_csv(products: List[Dict[str, Any]], prefer_p_tags: bool = True) -> str:
    """
    Generate CSV with BOM and sanitization
    Args:
        products: List of product dicts
        prefer_p_tags: Use <p> tags vs <br> tags
    Returns:
        CSV string with BOM
    """
    if not products:
        # Return empty CSV with default headers
        headers = ",".join(CSV_DEFAULT_HEADERS) + "\n"
        return CSV_BOM + headers

    # Collect all spec keys across all products
    all_spec_keys: Set[str] = set()
    for product in products:
        if specs := product.get("specifications"):
            if isinstance(specs, dict):
                all_spec_keys.update(specs.keys())

    spec_keys = sorted(all_spec_keys)

    # Build headers
    headers = CSV_DEFAULT_HEADERS + spec_keys

    # Build rows
    rows = []
    for product in products:
        # Get descriptions
        descriptions = product.get("descriptions", {})
        if not isinstance(descriptions, dict):
            descriptions = {}

        # Sanitize descriptions
        short = sanitize_for_csv(
            descriptions.get("shortDescription", ""),
            product.get("name", ""),
            product.get("sku", ""),
            prefer_p_tags
        )

        long = sanitize_for_csv(
            descriptions.get("longDescription", ""),
            product.get("name", ""),
            product.get("sku", ""),
            prefer_p_tags
        )

        meta = sanitize_for_csv(
            descriptions.get("metaDescription", ""),
            product.get("name", ""),
            product.get("sku", ""),
            True  # Always use <p> for meta
        )

        row = [
            str(product.get("sku", "")),
            str(product.get("barcode", "")),
            str(product.get("name", "")),
            short,
            long,
            meta,
            str(product.get("weightGrams", "")),
            str(product.get("weightHuman", ""))
        ]

        # Add spec columns
        specs = product.get("specifications", {})
        if not isinstance(specs, dict):
            specs = {}

        for key in spec_keys:
            row.append(str(specs.get(key, "")))

        rows.append(row)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)

    return CSV_BOM + output.getvalue()


def sanitize_for_csv(
    content: str,
    product_name: str,
    sku: str,
    prefer_p_tags: bool
) -> str:
    """
    Sanitize content for CSV export
    Args:
        content: HTML content to sanitize
        product_name: Product name for title enforcement
        sku: SKU for title enforcement
        prefer_p_tags: Use <p> tags vs <br> tags
    Returns:
        Sanitized content
    """
    if not content:
        return ""

    # Strip forbidden phrases
    content = strip_forbidden_phrases(content)

    # Normalize paragraph structure
    content = normalize_paragraphs(content, prefer_p_tags)

    # Enforce title in first sentence (replace SKU with product name)
    content = enforce_title_in_first_sentence(product_name, sku, content, prefer_p_tags)

    return content.strip()


def export_to_dict(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Export products to list of dictionaries (for JSON export)
    Args:
        products: List of product dicts
    Returns:
        List of export-ready dictionaries
    """
    export_data = []

    for product in products:
        descriptions = product.get("descriptions", {})
        if not isinstance(descriptions, dict):
            descriptions = {}

        # Build export dict
        export_item = {
            "sku": product.get("sku", ""),
            "barcode": product.get("barcode", ""),
            "name": product.get("name", ""),
            "brand": product.get("brand", ""),
            "category": product.get("category", ""),
            "shortDescription": descriptions.get("shortDescription", ""),
            "longDescription": descriptions.get("longDescription", ""),
            "metaDescription": descriptions.get("metaDescription", ""),
            "weightGrams": product.get("weightGrams", ""),
            "weightHuman": product.get("weightHuman", "")
        }

        # Add specifications
        specs = product.get("specifications", {})
        if isinstance(specs, dict):
            export_item["specifications"] = specs
        else:
            export_item["specifications"] = {}

        export_data.append(export_item)

    return export_data
