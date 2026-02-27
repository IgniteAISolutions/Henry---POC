"""
Shopify CSV Mapper for Earthfare
Maps generated product content to Shopify CSV format with metafields

IMPORTANT: Matrixify/Shopify requirements:
- Rich text metafields MUST be valid Shopify rich-text JSON
- List metafields MUST be proper JSON arrays
- Icons use metaobject references (icon_library.*)
- Body HTML left empty (Vector EPOS overwrites)
- Generated descriptions go to secondary_product_description
"""
import json
import re
import logging
from typing import Dict, List, Any, Optional, Union

from .csv_parser import clean_barcode

logger = logging.getLogger(__name__)

# Earthfare base URL for product URLs
EARTHFARE_BASE_URL = "https://www.earthfare.co.uk"

# Icon name to metaobject reference mapping
# These must match the icon_library metaobjects in Shopify
ICON_METAOBJECT_MAP = {
    "Palm Oil Free": "icon_library.palm-oil-free",
    "Organic": "icon_library.organic",
    "Vegan": "icon_library.vegan",
    "Fairtrade": "icon_library.fair-trade",
    "Fair Trade": "icon_library.fair-trade",
    "Gluten Free": "icon_library.gluten-free",
    "Sugar Free": "icon_library.sugar-free",
    "Dairy Free": "icon_library.dairy-free",
    "Seed Oil Free": "icon_library.seed-oil-free",
    "Nut Free": "icon_library.nut-free",
    "Low Waste": "icon_library.low-waste",
    "Compostable": "icon_library.compostable",
    "Local": "icon_library.local",
    "Vegetarian": "icon_library.vegetarian",
    "Raw": "icon_library.raw",
    "Keto": "icon_library.keto",
    "Paleo": "icon_library.paleo",
}


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


def format_icons_metaobject(icons: List[str]) -> str:
    """
    Format icons as Shopify metaobject references for Matrixify import.

    Matrixify format for list.metaobject_reference is comma-separated
    metaobject references, NOT a JSON array.

    e.g., "icon_library.vegan, icon_library.organic"

    Args:
        icons: List of icon name strings (e.g., ["Vegan", "Organic"])
    Returns:
        Comma-separated metaobject reference string
    """
    if not icons:
        return ""

    refs = []
    for icon in icons:
        icon_clean = str(icon).strip()
        if not icon_clean:
            continue

        ref = ICON_METAOBJECT_MAP.get(icon_clean)
        if ref:
            refs.append(ref)
        else:
            # Fallback: generate a slug-style reference
            slug = icon_clean.lower().replace(" ", "-")
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            ref = f"icon_library.{slug}"
            refs.append(ref)
            logger.warning(f"Unknown icon '{icon_clean}', using fallback ref: {ref}")

    if not refs:
        return ""

    return ", ".join(refs)


def format_nutrition_single_string(nutrition: Any) -> str:
    """
    Format nutrition as a single-element JSON array with one comma-separated string.

    Matrixify template format:
    ["Energy (kJ): 2430kJ, Energy (kcal): 586kcal, Fat: 43.2g, of which Saturates: 26.2g, ..."]

    Args:
        nutrition: Nutrition data in various formats (dict, str, list)
    Returns:
        JSON array string with single concatenated element
    """
    items = format_nutrition_for_metafield(nutrition)
    if not items:
        return ""

    # Join all nutrition items into one comma-separated string
    combined = ", ".join(items)

    # Wrap in single-element array
    result = json.dumps([combined], ensure_ascii=False)
    return result


def format_body_html(text: str) -> str:
    """
    Ensure body HTML is properly wrapped in <p> tags for Shopify

    Args:
        text: Plain text or HTML content
    Returns:
        HTML-formatted string with <p> tags
    """
    if not text:
        return ""

    # If already has <p> tags, return as-is
    if "<p>" in text.lower():
        return text

    # Wrap in <p> tags
    # Split by double newlines for paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not paragraphs:
        # Single paragraph
        return f"<p>{text.strip()}</p>"

    # Multiple paragraphs
    return "".join([f"<p>{p}</p>" for p in paragraphs])


def map_to_shopify_csv(product: Dict[str, Any]) -> Dict[str, str]:
    """
    Map generated product content to Matrixify-compatible Shopify CSV format

    Key differences from previous format:
    - Body HTML is left EMPTY (Vector EPOS overwrites it)
    - Generated description goes to secondary_product_description
    - Icons use metaobject references, not string lists
    - Includes SEO title_tag and description_tag
    - Includes URL column
    - Includes key_usps, search_boost, related/complementary products (empty for now)

    Args:
        product: Product dict with generated descriptions
    Returns:
        Dict with Matrixify CSV column names and values
    """
    name = product.get("name", "Unknown")
    logger.info(f"🗺️ [MAPPER] Mapping product: {name}")

    # Get descriptions from product
    descriptions = product.get("descriptions", {})

    # Get title - prefer generated, fallback to product name
    title = descriptions.get("title", "") or product.get("name", "")

    # Get brand - prefer generated, fallback to product data
    brand = descriptions.get("brand", "") or product.get("brand", "")

    # Get body HTML -- this goes to secondary_product_description, NOT Body HTML
    body_html_raw = descriptions.get("body_html", "") or descriptions.get("longDescription", "")
    secondary_description = format_body_html(body_html_raw)

    # SEO fields
    meta_description = descriptions.get("meta_description", "") or descriptions.get("metaDescription", "")
    seo_title = title  # title_tag is typically the product title

    # Generate product URL from handle
    shopify_handle = product.get("shopify_handle", "")
    handle = shopify_handle if shopify_handle else slugify(title)
    product_url = f"{EARTHFARE_BASE_URL}/products/{handle}" if handle else ""

    # Get dietary preferences
    dietary = descriptions.get("dietary_preferences", [])
    if not dietary and product.get("dietary"):
        dietary = product.get("dietary", [])

    # Get allergens
    allergens = product.get("allergens", [])

    # Get ingredients
    ingredients = product.get("ingredients", "")
    if isinstance(ingredients, list):
        ingredients = ", ".join(ingredients)

    # Get nutrition info - use new single-string format
    nutrition_raw = product.get("nutrition") or product.get("nutrition_shopify", [])

    # Get Earthfare icons
    icons = descriptions.get("icons", [])
    if not icons and product.get("icons"):
        icons = product.get("icons", [])

    # Get key USPs from short_description (benefit fragments split on <br>)
    key_usps = []
    short_desc = descriptions.get("short_description", "") or descriptions.get("shortDescription", "")
    if short_desc:
        # short_description is "Benefit 1<br>Benefit 2<br>Benefit 3"
        # Remove any wrapping <p> tags first
        short_desc_clean = re.sub(r'</?p>', '', short_desc)
        usps = [u.strip() for u in short_desc_clean.split("<br>") if u.strip()]
        # Also try <br/> and <br />
        if len(usps) <= 1:
            usps = [u.strip() for u in re.split(r'<br\s*/?>', short_desc_clean) if u.strip()]
        key_usps = usps

    # Build Shopify CSV row (Matrixify format)
    shopify_id = product.get("shopify_id", "")

    result = {
        "ID": shopify_id,
        "Title": title,
        "Body HTML": "",  # LEFT EMPTY - Vector EPOS overwrites this
        "Type": product.get("category", ""),
        "URL": product_url,
        "Metafield: title_tag [string]": seo_title,
        "Metafield: description_tag [string]": meta_description,
        "Metafield: custom.key_usps [list.single_line_text_field]": format_list_metafield(key_usps),
        "Metafield: shopify--discovery--product_search_boost.queries [list.single_line_text_field]": "",  # Empty - manual or future enhancement
        "Metafield: shopify--discovery--product_recommendation.related_products [list.product_reference]": "",  # Empty - manual curation
        "Metafield: shopify--discovery--product_recommendation.related_products_display [single_line_text_field]": "",  # Empty
        "Metafield: shopify--discovery--product_recommendation.complementary_products [list.product_reference]": "",  # Empty - manual curation
        "Metafield: custom.allergens [list.single_line_text_field]": format_list_metafield(allergens),
        "Metafield: pdp.ingredients [rich_text_field]": format_rich_text_metafield(ingredients),
        "Metafield: pdp.nutrition [list.single_line_text_field]": format_nutrition_single_string(nutrition_raw),
        "Metafield: custom.icons [list.metaobject_reference]": format_icons_metaobject(icons),
        "Metafield: custom.dietary_preferences [list.single_line_text_field]": format_list_metafield(dietary),
        "Metafield: custom.brand [single_line_text_field]": brand,
        "Metafield: custom.secondary_product_description [multi_line_text_field]": secondary_description,
    }

    # Log output for debugging
    logger.info(f"🗺️ [MAPPER] Output for {name}:")
    logger.info(f"   - URL: '{product_url}'")
    logger.info(f"   - Body HTML: (empty per Matrixify template)")
    logger.info(f"   - Secondary description length: {len(secondary_description)}")
    logger.info(f"   - Icons metaobject: {result['Metafield: custom.icons [list.metaobject_reference]'][:80] if result['Metafield: custom.icons [list.metaobject_reference]'] else 'empty'}")

    return result


def map_products_to_shopify(
    products: List[Dict[str, Any]],
    match_inventory: bool = True
) -> List[Dict[str, str]]:
    """
    Map multiple products to Shopify CSV format

    Args:
        products: List of product dicts with generated descriptions
        match_inventory: If True, match against existing Shopify inventory for updates

    Returns:
        List of Shopify CSV rows
    """
    # Optionally match against inventory for updates
    if match_inventory:
        try:
            from ..utils.inventory_matcher import load_inventory, match_products_to_inventory
            inventory = load_inventory()
            if inventory:
                products = match_products_to_inventory(products, inventory)
                logger.info(f"Matched products against {len(inventory)} inventory items")
        except Exception as e:
            logger.warning(f"Could not match against inventory: {e}")
    return [map_to_shopify_csv(product) for product in products]


# Shopify CSV column headers (Matrixify format)
# Must match the gold-standard Matrixify template exactly
# Body HTML left empty (Vector EPOS overwrites), descriptions go to secondary_product_description
SHOPIFY_CSV_HEADERS = [
    "ID",
    "Title",
    "Body HTML",
    "Type",
    "URL",
    "Metafield: title_tag [string]",
    "Metafield: description_tag [string]",
    "Metafield: custom.key_usps [list.single_line_text_field]",
    "Metafield: shopify--discovery--product_search_boost.queries [list.single_line_text_field]",
    "Metafield: shopify--discovery--product_recommendation.related_products [list.product_reference]",
    "Metafield: shopify--discovery--product_recommendation.related_products_display [single_line_text_field]",
    "Metafield: shopify--discovery--product_recommendation.complementary_products [list.product_reference]",
    "Metafield: custom.allergens [list.single_line_text_field]",
    "Metafield: pdp.ingredients [rich_text_field]",
    "Metafield: pdp.nutrition [list.single_line_text_field]",
    "Metafield: custom.icons [list.metaobject_reference]",
    "Metafield: custom.dietary_preferences [list.single_line_text_field]",
    "Metafield: custom.brand [single_line_text_field]",
    "Metafield: custom.secondary_product_description [multi_line_text_field]",
]
