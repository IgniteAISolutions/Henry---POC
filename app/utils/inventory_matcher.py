"""
Inventory Matcher for Earthfare Shopify Products
Load and match against existing Shopify inventory to enable updates vs creates
"""
import csv
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Path to inventory data
INVENTORY_DIR = Path(__file__).parent.parent.parent / "data" / "shopify_inventory"
INVENTORY_FILE = INVENTORY_DIR / "products_export.csv"


def load_inventory(filepath: Optional[Path] = None) -> List[Dict[str, str]]:
    """
    Load Shopify inventory CSV into memory

    Args:
        filepath: Optional path to CSV file (defaults to standard location)

    Returns:
        List of product dicts from CSV
    """
    filepath = filepath or INVENTORY_FILE

    if not filepath.exists():
        logger.warning(f"Inventory file not found: {filepath}")
        return []

    products = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                products.append(dict(row))

        logger.info(f"Loaded {len(products)} products from inventory")
        return products

    except Exception as e:
        logger.error(f"Failed to load inventory: {e}")
        return []


def build_lookup_index(inventory: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """
    Build lookup indexes for fast product matching

    Args:
        inventory: List of product dicts from load_inventory()

    Returns:
        Dict with indexes by handle, barcode, sku, and title
    """
    index = {
        "by_handle": {},
        "by_barcode": {},
        "by_sku": {},
        "by_title": {},
        "by_id": {}
    }

    for product in inventory:
        # Index by handle (primary key)
        handle = product.get("Handle", "").strip().lower()
        if handle:
            index["by_handle"][handle] = product

        # Index by barcode/EAN
        barcode = product.get("Variant Barcode", "").strip()
        if barcode:
            index["by_barcode"][barcode] = product

        # Index by SKU
        sku = product.get("Variant SKU", "").strip()
        if sku:
            index["by_sku"][sku] = product

        # Index by title (normalized)
        title = product.get("Title", "").strip().lower()
        if title:
            index["by_title"][title] = product

        # Index by Shopify ID
        product_id = product.get("ID", "").strip()
        if product_id:
            index["by_id"][product_id] = product

    logger.info(f"Built indexes: {len(index['by_handle'])} handles, "
                f"{len(index['by_barcode'])} barcodes, {len(index['by_sku'])} SKUs")

    return index


def find_product(
    inventory: List[Dict[str, str]],
    barcode: Optional[str] = None,
    sku: Optional[str] = None,
    handle: Optional[str] = None,
    title: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """
    Find a product in inventory by various identifiers

    Priority: barcode > sku > handle > title

    Args:
        inventory: List of product dicts
        barcode: Product barcode/EAN
        sku: Product SKU
        handle: Shopify handle
        title: Product title (fuzzy match)

    Returns:
        Matching product dict or None
    """
    index = build_lookup_index(inventory)

    # Try barcode first (most reliable)
    if barcode:
        barcode = barcode.strip()
        if barcode in index["by_barcode"]:
            return index["by_barcode"][barcode]

    # Try SKU
    if sku:
        sku = sku.strip()
        if sku in index["by_sku"]:
            return index["by_sku"][sku]

    # Try handle
    if handle:
        handle = handle.strip().lower()
        if handle in index["by_handle"]:
            return index["by_handle"][handle]

    # Try title (exact match, case-insensitive)
    if title:
        title = title.strip().lower()
        if title in index["by_title"]:
            return index["by_title"][title]

    return None


def match_products_to_inventory(
    products: List[Dict[str, Any]],
    inventory: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    Match a list of products against inventory, adding Shopify IDs where found

    Args:
        products: List of products to match
        inventory: Loaded inventory from load_inventory()

    Returns:
        Products with 'shopify_id' and 'shopify_handle' added where matched
    """
    index = build_lookup_index(inventory)
    matched_count = 0

    for product in products:
        barcode = product.get("barcode", "") or product.get("ean", "")
        sku = product.get("sku", "")
        name = product.get("name", "")

        # Try to find match
        existing = None

        if barcode and barcode in index["by_barcode"]:
            existing = index["by_barcode"][barcode]
        elif sku and sku in index["by_sku"]:
            existing = index["by_sku"][sku]
        elif name:
            name_lower = name.strip().lower()
            if name_lower in index["by_title"]:
                existing = index["by_title"][name_lower]

        if existing:
            product["shopify_id"] = existing.get("ID", "")
            product["shopify_handle"] = existing.get("Handle", "")
            product["_matched_in_inventory"] = True
            matched_count += 1
        else:
            product["_matched_in_inventory"] = False

    logger.info(f"Matched {matched_count}/{len(products)} products to inventory")
    return products


def get_inventory_stats(inventory: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Get statistics about the inventory

    Args:
        inventory: Loaded inventory

    Returns:
        Dict with inventory statistics
    """
    if not inventory:
        return {"total": 0, "error": "No inventory loaded"}

    stats = {
        "total_products": len(inventory),
        "with_barcode": 0,
        "with_sku": 0,
        "vendors": set(),
        "product_types": set(),
    }

    for product in inventory:
        if product.get("Variant Barcode", "").strip():
            stats["with_barcode"] += 1
        if product.get("Variant SKU", "").strip():
            stats["with_sku"] += 1
        if product.get("Vendor", "").strip():
            stats["vendors"].add(product["Vendor"])
        if product.get("Type", "").strip():
            stats["product_types"].add(product["Type"])

    stats["vendors"] = list(stats["vendors"])
    stats["product_types"] = list(stats["product_types"])
    stats["vendor_count"] = len(stats["vendors"])
    stats["type_count"] = len(stats["product_types"])

    return stats


def analyze_data_gaps(inventory: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Analyze inventory for missing data (nutrition, ingredients, etc.)

    Args:
        inventory: Loaded inventory

    Returns:
        Dict with gap analysis
    """
    gaps = {
        "missing_barcode": [],
        "missing_description": [],
        "missing_vendor": [],
        "total": len(inventory)
    }

    for product in inventory:
        handle = product.get("Handle", "Unknown")
        title = product.get("Title", "Unknown")

        if not product.get("Variant Barcode", "").strip():
            gaps["missing_barcode"].append({"handle": handle, "title": title})

        if not product.get("Body (HTML)", "").strip():
            gaps["missing_description"].append({"handle": handle, "title": title})

        if not product.get("Vendor", "").strip():
            gaps["missing_vendor"].append({"handle": handle, "title": title})

    gaps["missing_barcode_count"] = len(gaps["missing_barcode"])
    gaps["missing_description_count"] = len(gaps["missing_description"])
    gaps["missing_vendor_count"] = len(gaps["missing_vendor"])

    return gaps
