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
    Extracts all available data including dietary flags, ingredients, and romance copy
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
        row.get('Cat No') or
        row.get('cat_no') or
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
        "barcode": clean_barcode(extract_csv_field(row, ['barcode', 'Barcode', 'ean', 'EAN', 'upc', 'gtin', 'Variant Barcode'])),
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

    # Extract ingredients from CSV
    ingredients = extract_csv_field(row, ['Ingredients', 'ingredients', 'Ingredient', 'ingredient', 'contents', 'composition'])
    if ingredients:
        product["ingredients"] = ingredients

    # Extract Romance Copy as the detailed product description
    romance_copy = extract_csv_field(row, ['Romance Copy', 'romance_copy', 'Romance', 'romance', 'Long Description', 'long_description', 'detailed_description'])
    if romance_copy:
        product["romance_copy"] = romance_copy

    # Extract dietary preferences from boolean flags in CSV
    dietary = extract_dietary_from_csv(row)
    if dietary:
        product["dietary"] = dietary
        product["dietary_preferences"] = dietary  # Alias for Shopify export

    # Extract allergens if present
    allergens = extract_csv_field(row, ['Allergens', 'allergens', 'allergy_info', 'contains'])
    if allergens:
        product["allergens"] = parse_list_field(allergens)

    # Extract Earthfare icons (Palm Oil Free, Organic, Vegan, Fairtrade)
    # This must be called after dietary extraction since it uses dietary info
    icons = extract_icons_from_csv(row, product)
    if icons:
        product["icons"] = icons

    # Parse features
    features_str = extract_csv_field(row, ['features', 'Features', 'key_features'])
    if features_str:
        product["features"] = parse_list_field(features_str)

    # Parse benefits
    benefits_str = extract_csv_field(row, ['benefits', 'Benefits', 'advantages'])
    if benefits_str:
        product["benefits"] = parse_list_field(benefits_str)

    # Extract nutrition data from CSV columns (per 100g)
    nutrition = extract_nutrition_from_csv(row)
    if nutrition:
        product["nutrition"] = nutrition
        product["nutrition_source"] = "csv"

    return product


def extract_dietary_from_csv(row: Dict[str, str]) -> List[str]:
    """
    Extract dietary preferences from Yes/No columns in CSV

    Handles columns like: Organic, Gluten Free, Vegan, Dairy, Dairy Free,
    Sugar Free, Nut Free, Seed Oil Free, Vegetarian, etc.

    Args:
        row: CSV row as dictionary
    Returns:
        List of dietary preference strings
    """
    dietary = []

    # Map of CSV column names to standardized dietary labels
    dietary_columns = {
        # Organic
        'Organic': 'Organic',
        'organic': 'Organic',
        'Is Organic': 'Organic',
        'is_organic': 'Organic',

        # Gluten Free
        'Gluten Free': 'Gluten Free',
        'gluten_free': 'Gluten Free',
        'Gluten-Free': 'Gluten Free',
        'GlutenFree': 'Gluten Free',

        # Vegan
        'Vegan': 'Vegan',
        'vegan': 'Vegan',
        'Is Vegan': 'Vegan',
        'is_vegan': 'Vegan',

        # Vegetarian
        'Vegetarian': 'Vegetarian',
        'vegetarian': 'Vegetarian',
        'Is Vegetarian': 'Vegetarian',

        # Dairy Free
        'Dairy Free': 'Dairy Free',
        'dairy_free': 'Dairy Free',
        'Dairy-Free': 'Dairy Free',
        'DairyFree': 'Dairy Free',

        # Nut Free
        'Nut Free': 'Nut Free',
        'nut_free': 'Nut Free',
        'Nut-Free': 'Nut Free',
        'NutFree': 'Nut Free',

        # Sugar Free
        'Sugar Free': 'Sugar Free',
        'sugar_free': 'Sugar Free',
        'Sugar-Free': 'Sugar Free',
        'SugarFree': 'Sugar Free',

        # Seed Oil Free
        'Seed Oil Free': 'Seed Oil Free',
        'seed_oil_free': 'Seed Oil Free',

        # Raw
        'Raw': 'Raw',
        'raw': 'Raw',

        # Keto
        'Keto': 'Keto',
        'keto': 'Keto',

        # Paleo
        'Paleo': 'Paleo',
        'paleo': 'Paleo',
    }

    for column_name, dietary_label in dietary_columns.items():
        value = row.get(column_name, '')
        if value and is_yes_value(value):
            if dietary_label not in dietary:
                dietary.append(dietary_label)

    # Handle special case: "Dairy" column often means "Contains Dairy" (opposite of Dairy Free)
    # Only add "Dairy Free" if explicitly marked as No for Dairy or Yes for Dairy Free
    dairy_value = row.get('Dairy', '') or row.get('dairy', '')
    if dairy_value and is_no_value(dairy_value):
        if 'Dairy Free' not in dietary:
            dietary.append('Dairy Free')

    return dietary


def is_yes_value(value: str) -> bool:
    """Check if a value represents Yes/True"""
    if not value:
        return False
    v = str(value).strip().lower()
    return v in ['yes', 'true', '1', 'y', 'x', '✓', '✔']


def is_no_value(value: str) -> bool:
    """Check if a value represents No/False"""
    if not value:
        return False
    v = str(value).strip().lower()
    return v in ['no', 'false', '0', 'n', '-']


def clean_barcode(barcode: str) -> str:
    """
    Clean and normalize barcode string for consistent format

    Handles common issues:
    - Scientific notation from Excel (e.g., "5.06009E+12")
    - Floating point numbers (e.g., "5060093992311.0")
    - Spaces, dashes, dots
    - Leading/trailing whitespace
    - Non-numeric characters

    Args:
        barcode: Raw barcode string from CSV

    Returns:
        Clean numeric barcode string, or empty string if invalid
    """
    if not barcode:
        return ""

    barcode = str(barcode).strip()

    # Handle scientific notation (e.g., "5.06009E+12" from Excel)
    if 'e' in barcode.lower():
        try:
            # Convert scientific notation to integer
            barcode = str(int(float(barcode)))
        except (ValueError, OverflowError):
            pass

    # Handle floating point numbers (e.g., "5060093992311.0")
    if '.' in barcode:
        try:
            # Remove decimal part if it's .0
            float_val = float(barcode)
            if float_val == int(float_val):
                barcode = str(int(float_val))
            else:
                # Has actual decimal, just take integer part
                barcode = str(int(float_val))
        except (ValueError, OverflowError):
            # Not a valid number, try stripping after decimal
            barcode = barcode.split('.')[0]

    # Remove common separators and non-numeric characters
    barcode = barcode.replace(' ', '').replace('-', '').replace('.', '')

    # Extract only digits
    import re
    digits_only = re.sub(r'[^\d]', '', barcode)

    # Validate length (EAN-8, EAN-13, UPC-A are common)
    if len(digits_only) >= 8 and len(digits_only) <= 14:
        # Pad EAN-13 if leading zero was lost (common Excel issue)
        if len(digits_only) == 12:
            digits_only = '0' + digits_only
        return digits_only

    # Return original cleaned version if validation fails but has digits
    if digits_only:
        return digits_only

    return ""


def extract_nutrition_from_csv(row: Dict[str, str]) -> Dict[str, str]:
    """
    Extract nutrition data from CSV columns (per 100g values)

    Supports various column naming conventions for nutrition facts.

    Args:
        row: CSV row as dictionary

    Returns:
        Dict with nutrition values, e.g.:
        {
            "energy_kcal": "250",
            "energy_kj": "1046",
            "fat": "12.5",
            "saturates": "7.2",
            "carbohydrates": "28.0",
            "sugars": "18.5",
            "fibre": "2.1",
            "protein": "5.8",
            "salt": "0.3"
        }
    """
    nutrition = {}

    # Map of nutrition field to possible CSV column names
    nutrition_columns = {
        # Energy
        "energy_kcal": [
            "Energy (kcal)", "Energy kcal", "Energy(kcal)", "Kcal", "kcal",
            "Calories", "calories", "Cal", "Energy per 100g (kcal)",
            "energy_kcal", "energyKcal"
        ],
        "energy_kj": [
            "Energy (kJ)", "Energy kJ", "Energy(kJ)", "kJ", "KJ",
            "Energy per 100g (kJ)", "energy_kj", "energyKj"
        ],

        # Fat
        "fat": [
            "Fat", "fat", "Fat (g)", "Fat(g)", "Total Fat",
            "Fat per 100g", "fat_g"
        ],
        "saturates": [
            "Saturates", "saturates", "Saturated Fat", "Saturated fat",
            "of which saturates", "Sat Fat", "saturated_fat",
            "Saturates (g)", "Saturated Fat (g)"
        ],
        "monounsaturates": [
            "Mono-unsaturates", "Monounsaturates", "Monounsaturated Fat",
            "of which mono-unsaturates", "monounsaturated_fat"
        ],
        "polyunsaturates": [
            "Polyunsaturates", "Polyunsaturated Fat",
            "of which polyunsaturates", "polyunsaturated_fat"
        ],

        # Carbohydrates
        "carbohydrates": [
            "Carbohydrate", "Carbohydrates", "carbohydrates", "Carbs",
            "Carbohydrate (g)", "Carbohydrates (g)", "Total Carbohydrate",
            "carbohydrate_g"
        ],
        "sugars": [
            "Sugars", "sugars", "Sugar", "of which sugars",
            "Sugars (g)", "Sugar (g)", "Total Sugars", "sugars_g"
        ],
        "polyols": [
            "Polyols", "polyols", "of which polyols", "Sugar Alcohols"
        ],
        "starch": [
            "Starch", "starch", "of which starch"
        ],

        # Fibre
        "fibre": [
            "Fibre", "fibre", "Fiber", "fiber", "Dietary Fibre",
            "Fibre (g)", "Fiber (g)", "fibre_g"
        ],

        # Protein
        "protein": [
            "Protein", "protein", "Protein (g)", "protein_g"
        ],

        # Salt/Sodium
        "salt": [
            "Salt", "salt", "Salt (g)", "salt_g", "Sodium", "sodium"
        ],
    }

    for nutrition_key, column_names in nutrition_columns.items():
        for col_name in column_names:
            if col_name in row and row[col_name]:
                value = row[col_name].strip()
                # Skip empty or placeholder values
                if value and value.lower() not in ['n/a', 'none', '-', '']:
                    # Clean the value - remove units if present
                    clean_value = clean_nutrition_value(value)
                    if clean_value:
                        nutrition[nutrition_key] = clean_value
                        break  # Found a value, move to next field

    return nutrition if nutrition else {}


def clean_nutrition_value(value: str) -> str:
    """
    Clean nutrition value string - extract numeric value

    Args:
        value: Raw value like "12.5g", "250 kcal", "<0.1"

    Returns:
        Clean numeric string like "12.5", "250", "<0.1"
    """
    if not value:
        return ""

    import re

    value = str(value).strip()

    # Handle "less than" values
    if value.startswith("<") or value.startswith("less than"):
        # Extract the number after <
        match = re.search(r'[<]?\s*(\d+\.?\d*)', value)
        if match:
            return f"<{match.group(1)}"

    # Handle "trace" amounts
    if value.lower() in ['trace', 'tr', 'traces']:
        return "<0.1"

    # Extract numeric value (handles "12.5g", "250 kcal", etc.)
    match = re.search(r'(\d+\.?\d*)', value)
    if match:
        return match.group(1)

    return ""


def extract_icons_from_csv(row: Dict[str, str], product: Dict[str, Any]) -> List[str]:
    """
    Extract Earthfare icon metafield values from CSV row and product data.

    The 4 Earthfare icons are:
    - Palm Oil Free
    - Organic
    - Vegan
    - Fairtrade

    Detection sources:
    - CSV columns (e.g., 'Palm Oil Free', 'Fairtrade')
    - Dietary preferences already extracted
    - Text content (description, romance copy, ingredients)

    Args:
        row: CSV row as dictionary
        product: Product dict with already extracted fields
    Returns:
        List of icon names that apply to this product
    """
    icons = []

    # Get text fields for scanning
    text_fields = []
    for field in ['romance_copy', 'ingredients']:
        if product.get(field):
            text_fields.append(str(product[field]).lower())

    # Also check original row description fields
    for key in ['Description', 'description', 'Romance Copy', 'romance_copy', 'Long Description']:
        if row.get(key):
            text_fields.append(str(row[key]).lower())

    combined_text = ' '.join(text_fields)

    # 1. PALM OIL FREE
    # Check CSV column
    palm_oil_cols = ['Palm Oil Free', 'palm_oil_free', 'Palm-Oil-Free', 'PalmOilFree']
    for col in palm_oil_cols:
        if row.get(col) and is_yes_value(row.get(col, '')):
            if 'Palm Oil Free' not in icons:
                icons.append('Palm Oil Free')
            break
    # Check text content
    if 'Palm Oil Free' not in icons:
        if 'palm oil free' in combined_text or 'palm-oil-free' in combined_text:
            icons.append('Palm Oil Free')

    # 2. ORGANIC
    # Check if already in dietary preferences
    dietary = product.get('dietary', []) or product.get('dietary_preferences', [])
    if 'Organic' in dietary:
        icons.append('Organic')
    # Also check CSV columns and text
    elif row.get('Organic') and is_yes_value(row.get('Organic', '')):
        icons.append('Organic')
    elif 'organic' in combined_text and 'Organic' not in icons:
        # Be more specific - look for "organic" as certification, not just ingredient
        import re
        if re.search(r'\borganic\b', combined_text):
            icons.append('Organic')

    # 3. VEGAN
    # Check if already in dietary preferences
    if 'Vegan' in dietary:
        icons.append('Vegan')
    # Also check CSV columns
    elif row.get('Vegan') and is_yes_value(row.get('Vegan', '')):
        icons.append('Vegan')
    elif 'vegan' in combined_text and 'Vegan' not in icons:
        import re
        if re.search(r'\bvegan\b', combined_text):
            icons.append('Vegan')

    # 4. FAIRTRADE
    # Check CSV columns
    fairtrade_cols = ['Fairtrade', 'fairtrade', 'Fair Trade', 'fair_trade', 'FairTrade']
    for col in fairtrade_cols:
        if row.get(col) and is_yes_value(row.get(col, '')):
            if 'Fairtrade' not in icons:
                icons.append('Fairtrade')
            break
    # Check text content for fairtrade or rainforest alliance
    if 'Fairtrade' not in icons:
        import re
        if re.search(r'\b(fairtrade|fair[\s-]?trade|rainforest\s*alliance)\b', combined_text):
            icons.append('Fairtrade')

    return icons


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
