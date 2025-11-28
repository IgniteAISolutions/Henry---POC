"""
CSV Parser Service
Extracts product data from CSV files
"""
import csv
import io
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


async def process(file_content: bytes, category: str) -> List[Dict[str, Any]]:
    """
    Process CSV file and extract product data
    """
    try:
        text_content = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text_content = file_content.decode('latin-1')
        except UnicodeDecodeError:
            raise ValueError("Unable to decode CSV file - invalid encoding")

    logger.info(f"CSV Content (first 500 chars): {text_content[:500]}")

    reader = csv.DictReader(io.StringIO(text_content))
    
    # Strip whitespace from headers (fixes 'Description ' vs 'Description')
    if reader.fieldnames:
        reader.fieldnames = [f.strip() if f else f for f in reader.fieldnames]
    
    logger.info(f"CSV Headers: {reader.fieldnames}")

    products = []
    row_num = 0

    for row in reader:
        row_num += 1
        
        # Strip whitespace from keys and values
        row = {k.strip() if k else k: v.strip() if v else v for k, v in row.items()}
        
        if row_num <= 3:
            logger.info(f"Row {row_num}: {row}")

        try:
            product = parse_csv_row(row, category)
            if product:
                products.append(product)
            else:
                logger.warning(f"Row {row_num} produced no product")
        except Exception as e:
            logger.warning(f"Failed to parse row {row_num}: {e}")
            continue

    if not products:
        raise ValueError(f"No valid products found in CSV. Processed {row_num} rows with headers: {reader.fieldnames}")

    logger.info(f"Parsed {len(products)} products from CSV")
    return products


def parse_csv_row(row: Dict[str, str], category: str) -> Dict[str, Any]:
    """
    Parse a single CSV row into product dictionary
    """
    # Get product name - prioritize Description (most likely to have real name)
    name = (
        row.get('Description') or
        row.get('description') or
        row.get('Product Name') or
        row.get('Product Title') or
        row.get('name') or
        row.get('Name') or
        row.get('product_name') or
        row.get('title') or
        row.get('Title') or
        row.get('Short Description') or
        row.get('short_description')
    )
    
    # Get SKU from Code field (separate from name lookup)
    sku = (
        row.get('Code') or
        row.get('code') or
        row.get('SKU') or
        row.get('sku') or
        row.get('product_code') or
        row.get('item_code') or
        ""
    )

    if not name or not name.strip():
        logger.warning(f"No product name found in row, SKU: {sku}")
        return None

    product = {
        "name": name.strip(),
        "category": category,
        "sku": sku.strip() if sku else "",
        "barcode": extract_csv_field(row, ['barcode', 'Barcode', 'ean', 'EAN', 'upc', 'gtin']),
        "brand": extract_csv_field(row, ['brand', 'Brand', 'manufacturer']),
        "range": extract_csv_field(row, ['range', 'Range', 'collection', 'series']),
        "collection": extract_csv_field(row, ['collection', 'Collection']),
        "colour": extract_csv_field(row, ['colour', 'color', 'Colour', 'Color']),
        "pattern": extract_csv_field(row, ['pattern', 'Pattern', 'design']),
        "style": extract_csv_field(row, ['style', 'Style', 'type']),
        "finish": extract_csv_field(row, ['finish', 'Finish', 'surface']),
        "features": [],
        "benefits": [],
        "specifications": extract_specifications_from_row(row),
        "usage": extract_csv_field(row, ['usage', 'Usage', 'use', 'application']),
        "audience": extract_csv_field(row, ['audience', 'Audience', 'target', 'for']),
    }

    # Parse features
    features_str = extract_csv_field(row, ['features', 'Features', 'key_features'])
    if features_str:
        product["features"] = parse_list_field(features_str)

    # Parse benefits
    benefits_str = extract_csv_field(row, ['benefits', 'Benefits', 'advantages'])
    if benefits_str:
        product["benefits"] = parse_list_field(benefits_str)

    return product


def extract_csv_field(row: Dict[str, str], keys: List[str]) -> str:
    """Extract field from CSV row using multiple possible keys"""
    for key in keys:
        if key in row and row[key]:
            value = row[key].strip()
            if value and value.lower() not in ['n/a', 'none', 'null', '']:
                return value
    return ""


def parse_list_field(value: str) -> List[str]:
    """Parse list field from string (pipe or semicolon separated)"""
    if not value:
        return []
    if '|' in value:
        return [item.strip() for item in value.split('|') if item.strip()]
    if ';' in value:
        return [item.strip() for item in value.split(';') if item.strip()]
    if ',' in value and len(value) > 50:
        return [item.strip() for item in value.split(',') if item.strip()]
    return [value.strip()] if value.strip() else []


def extract_specifications_from_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Extract specifications from CSV row"""
    specs = {}
    spec_fields = {
        'material': ['material', 'Material', 'materials'],
        'dimensions': ['dimensions', 'Dimensions', 'size', 'Size'],
        'weight': ['weight', 'Weight'],
        'capacity': ['capacity', 'Capacity', 'volume'],
        'power': ['power', 'Power', 'wattage'],
        'origin': ['origin', 'Origin', 'made_in', 'country'],
        'warranty': ['warranty', 'Warranty', 'guarantee'],
        'care': ['care', 'Care', 'care_instructions']
    }
    for spec_key, possible_keys in spec_fields.items():
        value = extract_csv_field(row, possible_keys)
        if value:
            specs[spec_key] = value
    return specs
