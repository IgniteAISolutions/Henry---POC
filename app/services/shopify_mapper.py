"""
Shopify CSV Mapper for Earthfare
Maps generated product content to Shopify CSV format with metafields
"""
import json
import re
from typing import Dict, List, Any, Optional


def slugify(text: str) -> str:
    """
    Create URL-safe handle from product title
    Args:
        text: Product title or name
    Returns:
        URL-safe slug handle
    """
    if not text:
        return ""

    # Convert to lowercase
    slug = text.lower()

    # Replace special characters
    slug = slug.replace("'", "")
    slug = slug.replace("&", "and")

    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)

    # Remove any characters that aren't alphanumeric or hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    return slug


def format_list_metafield(items: List[str]) -> str:
    """
    Format as Shopify list metafield
    Args:
        items: List of strings
    Returns:
        JSON array string for Shopify metafield
    """
    if not items:
        return ""

    # Clean items and return as JSON array
    cleaned = [str(item).strip() for item in items if item]
    return json.dumps(cleaned)


def format_rich_text_metafield(text: str) -> str:
    """
    Format as Shopify rich text JSON metafield
    Args:
        text: Plain text or simple HTML
    Returns:
        Shopify rich text JSON structure
    """
    if not text:
        return ""

    # Strip HTML tags for rich text content
    plain_text = re.sub(r'<[^>]+>', '', text).strip()

    if not plain_text:
        return ""

    # Create Shopify rich text structure
    rich_text = {
        "type": "root",
        "children": [
            {
                "type": "paragraph",
                "children": [
                    {
                        "type": "text",
                        "value": plain_text
                    }
                ]
            }
        ]
    }

    return json.dumps(rich_text)


def parse_nutrition_info(text: str) -> List[str]:
    """
    Parse nutrition information from text
    Args:
        text: Nutrition text or ingredients
    Returns:
        List of nutrition facts
    """
    if not text:
        return []

    # Split by common delimiters
    items = re.split(r'[,;|]', text)
    return [item.strip() for item in items if item.strip()]


def map_to_shopify_csv(product: Dict[str, Any]) -> Dict[str, str]:
    """
    Map generated product content to Shopify CSV format
    Args:
        product: Product dict with generated descriptions
    Returns:
        Dict with Shopify CSV column names and values
    """
    # Get descriptions from product
    descriptions = product.get("descriptions", {})

    # Get title - prefer generated, fallback to product name
    title = descriptions.get("title", "") or product.get("name", "")

    # Get brand - prefer generated, fallback to product data
    brand = descriptions.get("brand", "") or product.get("brand", "")

    # Get body HTML
    body_html = descriptions.get("body_html", "") or descriptions.get("longDescription", "")

    # Get dietary preferences - prefer generated, fallback to normalized
    dietary = descriptions.get("dietary_preferences", [])
    if not dietary and product.get("dietary"):
        dietary = product.get("dietary", [])

    # Get allergens
    allergens = product.get("allergens", [])

    # Get ingredients
    ingredients = product.get("ingredients", "")
    if isinstance(ingredients, list):
        ingredients = ", ".join(ingredients)

    # Get nutrition info if available
    nutrition = product.get("nutrition", [])
    if isinstance(nutrition, str):
        nutrition = parse_nutrition_info(nutrition)

    # Build Shopify CSV row
    return {
        "ID": "",  # Leave blank for new products
        "Handle": slugify(title),
        "Title": title,
        "Body HTML": body_html,
        "Vendor": "Earthfare Supermarket",
        "Type": product.get("category", ""),
        "Variant Barcode": product.get("barcode", "") or product.get("ean", ""),
        "Metafield: custom.allergens [list.single_line_text_field]": format_list_metafield(allergens),
        "Metafield: pdp.ingredients [rich_text_field]": format_rich_text_metafield(ingredients),
        "Metafield: pdp.nutrition [list.single_line_text_field]": format_list_metafield(nutrition),
        "Metafield: custom.dietary_preferences [list.single_line_text_field]": format_list_metafield(dietary),
        "Metafield: custom.brand [single_line_text_field]": brand
    }


def map_products_to_shopify(products: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Map multiple products to Shopify CSV format
    Args:
        products: List of product dicts with generated descriptions
    Returns:
        List of Shopify CSV rows
    """
    return [map_to_shopify_csv(product) for product in products]


# Shopify CSV column headers
SHOPIFY_CSV_HEADERS = [
    "ID",
    "Handle",
    "Title",
    "Body HTML",
    "Vendor",
    "Type",
    "Variant Barcode",
    "Metafield: custom.allergens [list.single_line_text_field]",
    "Metafield: pdp.ingredients [rich_text_field]",
    "Metafield: pdp.nutrition [list.single_line_text_field]",
    "Metafield: custom.dietary_preferences [list.single_line_text_field]",
    "Metafield: custom.brand [single_line_text_field]"
]
