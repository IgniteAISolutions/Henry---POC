"""
Shopify CSV Mapper for Earthfare
Maps generated product content to Shopify CSV format with metafields

IMPORTANT: Matrixify/Shopify requirements:
- Rich text metafields MUST be valid Shopify rich-text JSON
- List metafields MUST be proper JSON arrays
- ID column removed for new product imports
"""
import json
import re
import logging
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)


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
    Format as Shopify list metafield (list.single_line_text_field)

    CRITICAL: Must output valid JSON array that Shopify/Matrixify will accept.
    e.g., ["Vegan","Gluten Free","Organic"]

    Args:
        items: List of strings
    Returns:
        JSON array string for Shopify metafield
    """
    if not items:
        return ""

    # Clean and validate items
    cleaned = []
    for item in items:
        if item is None:
            continue
        # Convert to string and strip whitespace
        text = str(item).strip()
        if not text:
            continue
        # Remove any control characters that could break JSON
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        # Limit length for single_line_text_field (Shopify limit)
        if len(text) > 255:
            text = text[:255]
        cleaned.append(text)

    if not cleaned:
        return ""

    # Use json.dumps for guaranteed valid JSON
    # ensure_ascii=False preserves UTF-8 characters properly
    result = json.dumps(cleaned, ensure_ascii=False)

    # Validate the output is parseable
    try:
        json.loads(result)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid list metafield JSON: {e}")
        return ""

    return result


def format_rich_text_metafield(text: str) -> str:
    """
    Format as Shopify rich text JSON metafield (rich_text_field)

    CRITICAL: Must output valid Shopify rich-text JSON every time.
    Matrixify will import it, but Shopify will reject malformed JSON.

    Shopify rich text structure:
    {
        "type": "root",
        "children": [
            {"type": "paragraph", "children": [{"type": "text", "value": "..."}]}
        ]
    }

    Args:
        text: Plain text or simple HTML
    Returns:
        Shopify rich text JSON structure
    """
    if not text:
        return ""

    # Strip HTML tags for rich text content
    plain_text = re.sub(r'<[^>]+>', ' ', text)

    # Normalize whitespace
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()

    if not plain_text:
        return ""

    # Remove control characters that break JSON
    plain_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', plain_text)

    # Handle newlines - convert to paragraph breaks
    paragraphs = [p.strip() for p in plain_text.split('\n') if p.strip()]

    if not paragraphs:
        paragraphs = [plain_text]

    # Build Shopify rich text structure with multiple paragraphs
    children = []
    for para in paragraphs:
        if para:
            children.append({
                "type": "paragraph",
                "children": [
                    {
                        "type": "text",
                        "value": para
                    }
                ]
            })

    if not children:
        return ""

    rich_text = {
        "type": "root",
        "children": children
    }

    # Use json.dumps with ensure_ascii=False for UTF-8 support
    # separators removes extra whitespace for compact output
    result = json.dumps(rich_text, ensure_ascii=False, separators=(',', ':'))

    # Validate the output is parseable
    try:
        parsed = json.loads(result)
        # Verify structure
        if parsed.get("type") != "root" or not parsed.get("children"):
            logger.error("Invalid rich text structure")
            return ""
    except json.JSONDecodeError as e:
        logger.error(f"Invalid rich text metafield JSON: {e}")
        return ""

    return result


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


def format_nutrition_for_metafield(nutrition: Any) -> List[str]:
    """
    Convert nutrition data (dict or str or list) to list format for Shopify metafield

    Args:
        nutrition: Nutrition data in various formats:
            - Dict: {"energy_kcal": "100", "fat": "5.2", ...}
            - String: "Energy 100kcal, Fat 5.2g"
            - List: ["Energy 100kcal", "Fat 5.2g"]

    Returns:
        List of formatted nutrition strings e.g. ["Energy: 100kcal", "Fat: 5.2g"]
    """
    if not nutrition:
        return []

    # Already a list
    if isinstance(nutrition, list):
        return [str(item).strip() for item in nutrition if item]

    # String - parse it
    if isinstance(nutrition, str):
        return parse_nutrition_info(nutrition)

    # Dict from nutrition_parser
    if isinstance(nutrition, dict):
        # UK nutrition label format mapping
        label_map = {
            "energy_kj": "Energy (kJ)",
            "energy_kcal": "Energy (kcal)",
            "fat": "Fat",
            "saturates": "of which Saturates",
            "carbohydrates": "Carbohydrate",
            "sugars": "of which Sugars",
            "fibre": "Fibre",
            "protein": "Protein",
            "salt": "Salt"
        }

        result = []
        # Order matters for UK labels
        order = ["energy_kj", "energy_kcal", "fat", "saturates",
                 "carbohydrates", "sugars", "fibre", "protein", "salt"]

        for key in order:
            value = nutrition.get(key)
            if value:
                label = label_map.get(key, key.replace("_", " ").title())
                # Add unit if not already present
                if key.startswith("energy"):
                    unit = "kJ" if "kj" in key else "kcal"
                    if unit not in str(value):
                        value = f"{value}{unit}"
                else:
                    if "g" not in str(value).lower():
                        value = f"{value}g"
                result.append(f"{label}: {value}")

        # Add any other keys not in our standard list
        for key, value in nutrition.items():
            if key not in order and value and not key.startswith("_"):
                label = key.replace("_", " ").title()
                result.append(f"{label}: {value}")

        return result

    return []


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

    # Get nutrition info if available - handle dict, string, or list
    nutrition_raw = product.get("nutrition") or product.get("nutrition_shopify", [])
    nutrition = format_nutrition_for_metafield(nutrition_raw)

    # Build Shopify CSV row
    # NOTE: ID column removed - this export is for NEW products only
    # For updates to existing products, use Shopify admin export and add ID column
    return {
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


# Shopify CSV column headers (for NEW product imports via Matrixify)
# NOTE: ID column intentionally omitted - only for new products
# For updates, export from Shopify admin to get IDs
SHOPIFY_CSV_HEADERS = [
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
