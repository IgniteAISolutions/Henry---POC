"""
Product structure normalization
Ensures consistent product data structure across all input types
"""
import re
from typing import Dict, List, Any, Optional


def normalize_product(product_data: Dict[str, Any], category: str) -> Dict[str, Any]:
    """
    Normalize a single product's structure
    Args:
        product_data: Raw product data from any source
        category: Product category
    Returns:
        Normalized product dictionary
    """
    normalized = {
        "sku": extract_field(product_data, ["sku", "SKU", "product_code", "item_code"]),
        "barcode": extract_field(product_data, ["barcode", "ean", "EAN", "upc", "gtin"]),
        "name": extract_field(product_data, ["name", "title", "product_name", "productName"], required=True),
        "brand": extract_field(product_data, ["brand", "manufacturer", "make"]),
        "category": category,
        "range": extract_field(product_data, ["range", "collection", "series"]),
        "collection": extract_field(product_data, ["collection", "line"]),
        "colour": extract_field(product_data, ["colour", "color", "finish_colour"]),
        "pattern": extract_field(product_data, ["pattern", "design"]),
        "style": extract_field(product_data, ["style", "type"]),
        "finish": extract_field(product_data, ["finish", "surface"]),
        "features": normalize_list_field(product_data, ["features", "key_features", "highlights"]),
        "benefits": normalize_list_field(product_data, ["benefits", "advantages"]),
        "specifications": normalize_specifications(product_data),
        "isNonStick": detect_non_stick(product_data),
        "usage": extract_field(product_data, ["usage", "use", "application"]),
        "audience": extract_field(product_data, ["audience", "target", "for"]),
        "weightGrams": extract_weight_grams(product_data),
        "weightHuman": extract_weight_human(product_data),
    }

    # Initialize descriptions if not present
    if "descriptions" not in normalized or not normalized["descriptions"]:
        normalized["descriptions"] = {
            "shortDescription": "",
            "metaDescription": "",
            "longDescription": ""
        }

    return normalized


def normalize_products(products: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """
    Normalize multiple products
    Args:
        products: List of raw product data
        category: Product category
    Returns:
        List of normalized products
    """
    return [normalize_product(p, category) for p in products]


def extract_field(data: Dict[str, Any], keys: List[str], required: bool = False) -> Optional[str]:
    """
    Extract a field from product data using multiple possible key names
    Args:
        data: Product data dictionary
        keys: List of possible key names to check
        required: If True, raise error if field not found
    Returns:
        Field value or None
    """
    for key in keys:
        # Check direct key
        if key in data and data[key]:
            value = str(data[key]).strip()
            if value and value.lower() not in ["n/a", "none", "null", ""]:
                return value

        # Check case-insensitive key
        for data_key in data.keys():
            if data_key.lower() == key.lower() and data[data_key]:
                value = str(data[data_key]).strip()
                if value and value.lower() not in ["n/a", "none", "null", ""]:
                    return value

    if required:
        raise ValueError(f"Required field not found. Tried keys: {keys}")

    return None


def normalize_list_field(data: Dict[str, Any], keys: List[str]) -> List[str]:
    """
    Extract and normalize a list field
    Args:
        data: Product data dictionary
        keys: List of possible key names
    Returns:
        Normalized list of strings
    """
    for key in keys:
        if key in data:
            value = data[key]

            # Already a list
            if isinstance(value, list):
                return [str(v).strip() for v in value if v]

            # String that needs splitting
            if isinstance(value, str):
                # Try splitting by common delimiters
                if '|' in value:
                    return [v.strip() for v in value.split('|') if v.strip()]
                elif ';' in value:
                    return [v.strip() for v in value.split(';') if v.strip()]
                elif ',' in value and len(value) > 50:  # Avoid splitting single values with commas
                    return [v.strip() for v in value.split(',') if v.strip()]
                else:
                    return [value.strip()] if value.strip() else []

    return []


def normalize_specifications(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize product specifications
    Args:
        data: Product data dictionary
    Returns:
        Normalized specifications dictionary
    """
    specs = {}

    # If there's a dedicated specifications object
    if "specifications" in data and isinstance(data["specifications"], dict):
        specs.update(data["specifications"])

    # Common specification fields
    spec_mapping = {
        "material": ["material", "materials", "construction", "made_from"],
        "bladeLength": ["blade_length", "bladeLength", "blade"],
        "dimensions": ["dimensions", "size", "measurements", "dims"],
        "weight": ["weight", "weight_text"],
        "weightKg": ["weight_kg", "weightKg", "weight_kilograms"],
        "capacity": ["capacity", "volume", "size"],
        "powerW": ["power", "power_w", "powerW", "wattage", "watts"],
        "programs": ["programs", "settings", "modes", "functions"],
        "origin": ["origin", "made_in", "country", "country_of_origin"],
        "madeIn": ["made_in", "madeIn", "origin", "manufactured_in"],
        "guarantee": ["guarantee", "warranty", "guarantee_years"],
        "warranty": ["warranty", "guarantee"],
        "care": ["care", "care_instructions", "cleaning", "maintenance"]
    }

    for spec_key, possible_keys in spec_mapping.items():
        value = extract_field(data, possible_keys)
        if value:
            specs[spec_key] = value

    # Clean up dimensions if present
    if "dimensions" in specs:
        specs["dimensions"] = normalize_dimensions(specs["dimensions"])

    # Parse power as integer if present
    if "powerW" in specs:
        specs["powerW"] = parse_integer(specs["powerW"])

    # Parse weight as float if present
    if "weightKg" in specs:
        specs["weightKg"] = parse_float(specs["weightKg"])

    return specs


def normalize_dimensions(dim_str: str) -> str:
    """
    Normalize dimension strings to consistent format
    Args:
        dim_str: Dimension string (various formats)
    Returns:
        Normalized dimension string
    """
    if not dim_str:
        return ""

    # Common patterns: "30x20x10cm", "30 x 20 x 10 cm", "H30 W20 D10"
    # Normalize to: "30(H) x 20(W) x 10(D) cm"

    # Extract numbers
    numbers = re.findall(r'\d+\.?\d*', dim_str)

    if len(numbers) == 3:
        # Try to detect if H/W/D labels are present
        if re.search(r'[HhØ]', dim_str):
            return f"{numbers[0]}(H) x {numbers[1]}(W) x {numbers[2]}(D) cm"
        else:
            # Assume order is L x W x H or H x W x D
            return f"{numbers[0]} x {numbers[1]} x {numbers[2]} cm"
    elif len(numbers) == 2:
        return f"{numbers[0]} x {numbers[1]} cm"
    elif len(numbers) == 1:
        return f"{numbers[0]} cm"

    # Return as-is if we can't parse
    return dim_str


def detect_non_stick(data: Dict[str, Any]) -> bool:
    """
    Detect if product has non-stick coating
    Args:
        data: Product data dictionary
    Returns:
        True if product is non-stick
    """
    # Check various fields for non-stick mentions
    check_fields = [
        "name", "title", "description", "features",
        "coating", "finish", "material", "specifications"
    ]

    non_stick_patterns = [
        r'non-stick', r'nonstick', r'non stick',
        r'teflon', r'ptfe', r'ceramic coated'
    ]

    for field in check_fields:
        if field in data:
            value = str(data[field]).lower()
            for pattern in non_stick_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    return True

    return False


def extract_weight_grams(data: Dict[str, Any]) -> Optional[int]:
    """
    Extract weight in grams
    Args:
        data: Product data dictionary
    Returns:
        Weight in grams or None
    """
    # Check for weight_grams field
    weight_grams = extract_field(data, ["weight_grams", "weightGrams", "grams"])
    if weight_grams:
        return parse_integer(weight_grams)

    # Check for weight in kg
    weight_kg = extract_field(data, ["weight_kg", "weightKg", "weight_kilograms"])
    if weight_kg:
        kg_value = parse_float(weight_kg)
        if kg_value:
            return int(kg_value * 1000)

    # Check for weight text and try to parse
    weight_text = extract_field(data, ["weight", "weight_text"])
    if weight_text:
        return parse_weight_to_grams(weight_text)

    return None


def extract_weight_human(data: Dict[str, Any]) -> Optional[str]:
    """
    Extract human-readable weight
    Args:
        data: Product data dictionary
    Returns:
        Human-readable weight string
    """
    weight_human = extract_field(data, ["weight_human", "weightHuman", "weight_text", "weight"])
    if weight_human:
        return weight_human

    # Generate from grams if available
    grams = extract_weight_grams(data)
    if grams:
        if grams >= 1000:
            kg = grams / 1000
            return f"{kg:.2f}kg"
        else:
            return f"{grams}g"

    return None


def parse_weight_to_grams(weight_str: str) -> Optional[int]:
    """
    Parse weight string to grams
    Args:
        weight_str: Weight string like "2.5kg", "500g", "1.2 kg"
    Returns:
        Weight in grams
    """
    if not weight_str:
        return None

    weight_str = weight_str.lower().strip()

    # Try to extract number and unit
    match = re.search(r'(\d+\.?\d*)\s*(kg|g|grams?|kilograms?)', weight_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2)

        if unit.startswith('k'):
            return int(value * 1000)
        else:
            return int(value)

    return None


def parse_integer(value: Any) -> Optional[int]:
    """
    Parse value to integer
    Args:
        value: Value to parse
    Returns:
        Integer or None
    """
    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        # Remove non-numeric characters except decimal point
        cleaned = re.sub(r'[^\d.]', '', value)
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None

    return None


def parse_float(value: Any) -> Optional[float]:
    """
    Parse value to float
    Args:
        value: Value to parse
    Returns:
        Float or None
    """
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Remove non-numeric characters except decimal point
        cleaned = re.sub(r'[^\d.]', '', value)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    return None
