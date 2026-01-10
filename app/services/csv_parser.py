"""
CSV Parser Service
Extracts product data from CSV files
Supports both headerless and header-based CSV formats
"""
import csv
import io
import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# EarthFare expected column order for headerless CSVs
# Based on supplier export format:
# Brand, Code, Barcode, BrandShort, Description, ImagePath, [Yes/No flags], Category
HEADERLESS_COLUMNS = [
    'brand',        # 0: Brand name (e.g., "Ainsworths")
    'code',         # 1: SKU/Code (e.g., "37136")
    'barcode',      # 2: Barcode/EAN (e.g., "5.03E+12" or "5030000123456")
    'brand_short',  # 3: Brand short name
    'description',  # 4: Product description/name
    'image_path',   # 5: Image file path
    'flag_1',       # 6: Yes/No flag
    'flag_2',       # 7: Yes/No flag
    'flag_3',       # 8: Yes/No flag
    'flag_4',       # 9: Yes/No flag
    'flag_5',       # 10: Yes/No flag
    'flag_6',       # 11: Yes/No flag
    'flag_7',       # 12: Extra field (often "-")
    'category',     # 13: Category
]


def detect_has_headers(first_row: List[str]) -> bool:
    """
    Detect if the first row looks like headers or data.

    Headers typically:
    - Contain words like 'name', 'sku', 'code', 'description', 'brand', 'barcode'
    - Don't contain numeric values that look like SKUs or barcodes
    - Don't contain 'Yes'/'No' values

    Returns:
        True if first row appears to be headers, False if it's data
    """
    if not first_row:
        return False

    header_keywords = [
        'name', 'sku', 'code', 'description', 'brand', 'barcode', 'ean',
        'title', 'product', 'category', 'price', 'weight', 'image'
    ]

    # Check for header-like keywords (case insensitive)
    first_row_lower = [str(cell).lower().strip() for cell in first_row]

    keyword_matches = sum(
        1 for cell in first_row_lower
        if any(kw in cell for kw in header_keywords)
    )

    # If 2+ cells look like header keywords, it's probably headers
    if keyword_matches >= 2:
        logger.info(f"Detected headers (keyword matches: {keyword_matches})")
        return True

    # Check for data indicators (numeric codes, Yes/No, barcodes)
    data_indicators = 0
    for cell in first_row:
        cell_str = str(cell).strip()
        # Numeric SKU-like values
        if cell_str.isdigit() and len(cell_str) >= 4:
            data_indicators += 1
        # Scientific notation (barcode)
        if re.match(r'^\d+\.?\d*[eE]\+?\d+$', cell_str):
            data_indicators += 1
        # Yes/No values
        if cell_str.lower() in ['yes', 'no']:
            data_indicators += 1

    if data_indicators >= 2:
        logger.info(f"Detected headerless CSV (data indicators: {data_indicators})")
        return False

    # Default: assume has headers
    return True


def fix_scientific_barcode(value: str) -> str:
    """
    Convert scientific notation barcodes to full numbers.
    E.g., "5.03E+12" -> "5030000000000"
    """
    if not value:
        return ""

    value = str(value).strip()

    # Check for scientific notation
    if re.match(r'^[\d.]+[eE][+\-]?\d+$', value):
        try:
            # Convert to int to remove decimal, then to string
            return str(int(float(value)))
        except (ValueError, OverflowError):
            return value

    return value


def parse_headerless_row(row: List[str], category: str) -> Optional[Dict[str, Any]]:
    """
    Parse a headerless CSV row using positional column mapping.

    Expected format:
    Brand, Code, Barcode, BrandShort, Description, ImagePath, [flags...], Category
    """
    if not row or len(row) < 5:
        return None

    # Map positional values
    def get_col(idx: int) -> str:
        if idx < len(row):
            val = str(row[idx]).strip() if row[idx] else ""
            return val if val.lower() not in ['', 'none', 'n/a', 'null'] else ""
        return ""

    brand = get_col(0)
    code = get_col(1)
    barcode = fix_scientific_barcode(get_col(2))
    description = get_col(4)  # Column 4 is the product name/description

    # Use last column as category if provided, otherwise use passed category
    row_category = get_col(len(row) - 1) if len(row) > 6 else ""
    final_category = row_category if row_category and row_category != '-' else category

    if not description:
        logger.warning(f"No description found in row, Code: {code}")
        return None

    return {
        "name": description,
        "category": final_category,
        "sku": code,
        "barcode": barcode,
        "brand": brand,
        "range": "",
        "collection": "",
        "colour": "",
        "pattern": "",
        "style": "",
        "finish": "",
        "features": [],
        "benefits": [],
        "specifications": {},
        "usage": "",
        "audience": "",
    }


async def process(file_content: bytes, category: str) -> List[Dict[str, Any]]:
    """
    Process CSV file and extract product data.
    Auto-detects headerless vs header-based CSV formats.
    """
    try:
        text_content = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text_content = file_content.decode('latin-1')
        except UnicodeDecodeError:
            raise ValueError("Unable to decode CSV file - invalid encoding")

    logger.info(f"CSV Content (first 500 chars): {text_content[:500]}")

    # First, read all rows to detect format
    all_rows = list(csv.reader(io.StringIO(text_content)))

    if not all_rows:
        raise ValueError("CSV file is empty")

    # Detect if first row is headers or data
    has_headers = detect_has_headers(all_rows[0])

    products = []

    if has_headers:
        # Use DictReader for header-based CSV
        logger.info("Processing CSV with headers")
        reader = csv.DictReader(io.StringIO(text_content))

        # Strip whitespace from headers
        if reader.fieldnames:
            reader.fieldnames = [f.strip() if f else f for f in reader.fieldnames]

        logger.info(f"CSV Headers: {reader.fieldnames}")

        row_num = 0
        for row in reader:
            row_num += 1
            row = {k.strip() if k else k: v.strip() if v else v for k, v in row.items()}

            if row_num <= 3:
                logger.info(f"Row {row_num}: {row}")

            try:
                product = parse_csv_row(row, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse row {row_num}: {e}")
                continue
    else:
        # Process headerless CSV using positional mapping
        logger.info("Processing headerless CSV")

        for row_num, row in enumerate(all_rows, 1):
            if row_num <= 3:
                logger.info(f"Row {row_num}: {row}")

            try:
                product = parse_headerless_row(row, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse row {row_num}: {e}")
                continue

    if not products:
        raise ValueError(f"No valid products found in CSV. Processed {len(all_rows)} rows.")

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
