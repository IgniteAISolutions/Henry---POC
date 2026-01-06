"""
Product structure normalization for EarthFare
Ensures consistent product data structure for natural grocery products
"""
import re
from typing import Dict, List, Any, Optional


def normalize_product(product_data: Dict[str, Any], category: str) -> Dict[str, Any]:
    """
    Normalize a single product's structure for EarthFare grocery products
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
        "brand": extract_field(product_data, ["brand", "manufacturer", "producer", "supplier"]),
        "category": category,
        # EarthFare-specific fields
        "producer": extract_field(product_data, ["producer", "supplier", "maker", "farm", "grower"]),
        "region": extract_field(product_data, ["region", "location", "source_region", "area"]),
        "ingredients": extract_field(product_data, ["ingredients", "contents", "composition"]),
        "dietary": normalize_dietary_info(product_data),
        "certifications": normalize_certifications(product_data),
        "allergens": normalize_list_field(product_data, ["allergens", "allergy_info", "contains"]),
        # Common fields
        "features": normalize_list_field(product_data, ["features", "key_features", "highlights"]),
        "benefits": normalize_list_field(product_data, ["benefits", "advantages"]),
        "specifications": normalize_specifications(product_data),
        "usage": extract_field(product_data, ["usage", "use", "serving_suggestion", "application"]),
        "audience": extract_field(product_data, ["audience", "target", "for", "suitable_for"]),
        "storage": extract_field(product_data, ["storage", "storage_instructions", "keep", "store"]),
        "servings": extract_field(product_data, ["servings", "portions", "serves"]),
        "weightGrams": extract_weight_grams(product_data),
        "weightHuman": extract_weight_human(product_data),
        "volume": extract_field(product_data, ["volume", "ml", "litres", "liters"]),
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


def normalize_dietary_info(data: Dict[str, Any]) -> List[str]:
    """
    Extract and normalize dietary information for EarthFare products
    Args:
        data: Product data dictionary
    Returns:
        List of dietary attributes (e.g., ['Vegan', 'Gluten Free'])
    """
    dietary = []

    # Check dedicated dietary field
    dietary_field = extract_field(data, ["dietary", "dietary_info", "diet"])
    if dietary_field:
        dietary.extend([d.strip() for d in dietary_field.split(',') if d.strip()])

    # Check boolean flags
    dietary_flags = {
        "vegan": ["vegan", "isVegan", "is_vegan"],
        "vegetarian": ["vegetarian", "isVegetarian", "is_vegetarian"],
        "gluten_free": ["gluten_free", "glutenFree", "isGlutenFree"],
        "dairy_free": ["dairy_free", "dairyFree", "isDairyFree"],
        "nut_free": ["nut_free", "nutFree", "isNutFree"],
        "organic": ["organic", "isOrganic", "is_organic"],
        "raw": ["raw", "isRaw", "is_raw"],
        "keto": ["keto", "isKeto", "is_keto"],
        "paleo": ["paleo", "isPaleo", "is_paleo"]
    }

    dietary_labels = {
        "vegan": "Vegan",
        "vegetarian": "Vegetarian",
        "gluten_free": "Gluten Free",
        "dairy_free": "Dairy Free",
        "nut_free": "Nut Free",
        "organic": "Organic",
        "raw": "Raw",
        "keto": "Keto",
        "paleo": "Paleo"
    }

    for diet_key, field_names in dietary_flags.items():
        for field in field_names:
            if field in data and data[field]:
                value = data[field]
                if isinstance(value, bool) and value:
                    if dietary_labels[diet_key] not in dietary:
                        dietary.append(dietary_labels[diet_key])
                elif isinstance(value, str) and value.lower() in ['true', 'yes', '1']:
                    if dietary_labels[diet_key] not in dietary:
                        dietary.append(dietary_labels[diet_key])

    # Scan text fields for dietary mentions
    text_fields = ["name", "title", "description", "features"]
    dietary_patterns = {
        r'\bvegan\b': "Vegan",
        r'\bvegetarian\b': "Vegetarian",
        r'\bgluten[- ]?free\b': "Gluten Free",
        r'\bdairy[- ]?free\b': "Dairy Free",
        r'\bnut[- ]?free\b': "Nut Free",
        r'\borganic\b': "Organic"
    }

    for field in text_fields:
        if field in data and data[field]:
            text = str(data[field]).lower()
            for pattern, label in dietary_patterns.items():
                if re.search(pattern, text, re.IGNORECASE) and label not in dietary:
                    dietary.append(label)

    return dietary


def normalize_certifications(data: Dict[str, Any]) -> List[str]:
    """
    Extract and normalize product certifications for EarthFare
    Args:
        data: Product data dictionary
    Returns:
        List of certifications (e.g., ['Organic', 'Fairtrade', 'Soil Association'])
    """
    certifications = []

    # Check dedicated certifications field
    cert_field = normalize_list_field(data, ["certifications", "certificates", "accreditations"])
    certifications.extend(cert_field)

    # Check for common certifications in text fields
    text_fields = ["name", "title", "description", "features"]
    cert_patterns = {
        r'\borganic\b': "Organic",
        r'\bfairtrade\b': "Fairtrade",
        r'\bsoil association\b': "Soil Association",
        r'\bnon[- ]?gmo\b': "Non-GMO",
        r'\brainforest alliance\b': "Rainforest Alliance",
        r'\bb[- ]?corp\b': "B Corp",
        r'\bleaping bunny\b': "Leaping Bunny",
        r'\bvegan society\b': "Vegan Society",
        r'\bvegetarian society\b': "Vegetarian Society",
        r'\bkosher\b': "Kosher",
        r'\bhalal\b': "Halal"
    }

    for field in text_fields:
        if field in data and data[field]:
            text = str(data[field]).lower()
            for pattern, label in cert_patterns.items():
                if re.search(pattern, text, re.IGNORECASE) and label not in certifications:
                    certifications.append(label)

    return certifications


def normalize_specifications(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize product specifications for EarthFare grocery products
    Args:
        data: Product data dictionary
    Returns:
        Normalized specifications dictionary
    """
    specs = {}

    # If there's a dedicated specifications object
    if "specifications" in data and isinstance(data["specifications"], dict):
        specs.update(data["specifications"])

    # EarthFare specification fields - focused on food/grocery products
    spec_mapping = {
        "weight": ["weight", "weight_text", "net_weight"],
        "volume": ["volume", "ml", "litres", "liters", "capacity"],
        "origin": ["origin", "made_in", "country", "country_of_origin", "source"],
        "producer": ["producer", "supplier", "farm", "grower", "maker"],
        "region": ["region", "location", "source_region"],
        "ingredients": ["ingredients", "contents", "composition"],
        "storage": ["storage", "storage_instructions", "keep", "store"],
        "servings": ["servings", "portions", "serves", "serving_size"],
        "dosage": ["dosage", "dose", "recommended_dose"],
        "usage": ["usage", "use", "serving_suggestion", "directions"]
    }

    for spec_key, possible_keys in spec_mapping.items():
        value = extract_field(data, possible_keys)
        if value:
            specs[spec_key] = value

    return specs


def normalize_volume(vol_str: str) -> Optional[str]:
    """
    Normalize volume strings to consistent format for beverages and liquids
    Args:
        vol_str: Volume string (various formats)
    Returns:
        Normalized volume string (e.g., "500ml", "1L")
    """
    if not vol_str:
        return None

    vol_str = vol_str.lower().strip()

    # Extract number and unit
    match = re.search(r'(\d+\.?\d*)\s*(ml|l|litre|liter|cl)', vol_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2)

        if unit in ['l', 'litre', 'liter']:
            if value < 1:
                return f"{int(value * 1000)}ml"
            return f"{value}L"
        elif unit == 'cl':
            return f"{int(value * 10)}ml"
        else:  # ml
            if value >= 1000:
                return f"{value / 1000}L"
            return f"{int(value)}ml"

    return vol_str


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
