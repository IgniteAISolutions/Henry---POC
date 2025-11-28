"""
Text Processor Service
NLP processing for free-form text input
"""
import logging
import re
from typing import List, Dict, Any

from ..config import TEXT_MIN_LENGTH, TEXT_MAX_LENGTH

logger = logging.getLogger(__name__)


async def process(text: str, category: str) -> List[Dict[str, Any]]:
    """
    Process free-form text and extract product data using NLP
    Args:
        text: Free-form text containing product information
        category: Product category
    Returns:
        List of product dictionaries
    Raises:
        ValueError: If text is invalid or too short/long
    """
    # Validate text length
    if len(text) < TEXT_MIN_LENGTH:
        raise ValueError(f"Text too short (minimum {TEXT_MIN_LENGTH} characters)")

    if len(text) > TEXT_MAX_LENGTH:
        raise ValueError(f"Text too long (maximum {TEXT_MAX_LENGTH} characters)")

    logger.info(f"Processing {len(text)} characters of text")

    # Parse text into product data
    products = parse_text(text, category)

    if not products:
        raise ValueError("Could not extract product data from text")

    logger.info(f"Extracted {len(products)} product(s) from text")

    return products


def parse_text(text: str, category: str) -> List[Dict[str, Any]]:
    """
    Parse free-form text into product data
    Args:
        text: Free-form text
        category: Product category
    Returns:
        List of product dictionaries
    """
    # Try to detect if text contains multiple products
    products = split_into_products(text)

    if len(products) > 1:
        logger.info(f"Detected {len(products)} products in text")
        return [parse_single_product(p, category) for p in products]
    else:
        # Single product
        return [parse_single_product(text, category)]


def split_into_products(text: str) -> List[str]:
    """
    Split text into multiple products if applicable
    Args:
        text: Free-form text
    Returns:
        List of product text blocks
    """
    # Look for common separators
    separators = [
        r'\n\s*---+\s*\n',  # --- separator
        r'\n\s*===+\s*\n',  # === separator
        r'\n\s*\*\*\*+\s*\n',  # *** separator
        r'\nProduct \d+:',  # Product 1:, Product 2:, etc.
    ]

    for separator in separators:
        parts = re.split(separator, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]

    # No separators found, return as single product
    return [text]


def parse_single_product(text: str, category: str) -> Dict[str, Any]:
    """
    Parse single product from text
    Args:
        text: Text for single product
        category: Product category
    Returns:
        Product dictionary
    """
    product = {
        "name": extract_name_from_text(text),
        "category": category,
        "sku": extract_sku_from_text(text),
        "barcode": extract_barcode_from_text(text),
        "brand": extract_brand_from_text(text),
        "features": extract_features_from_text(text),
        "benefits": extract_benefits_from_text(text),
        "specifications": extract_specs_from_text(text),
        "usage": extract_usage_from_text(text),
    }

    # If no name found, use first line
    if not product["name"]:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines:
            product["name"] = lines[0][:100]
        else:
            product["name"] = "Product from text"

    return product


def extract_name_from_text(text: str) -> str:
    """Extract product name from text"""

    # Look for explicit name patterns
    patterns = [
        r'Product Name:\s*(.+?)(?:\n|$)',
        r'Name:\s*(.+?)(?:\n|$)',
        r'Title:\s*(.+?)(?:\n|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Use first substantial line
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        # Skip short lines and lines that look like labels
        if len(line) > 10 and ':' not in line[:30]:
            return line[:100]

    return ""


def extract_sku_from_text(text: str) -> str:
    """Extract SKU from text"""

    patterns = [
        r'SKU:\s*([A-Z0-9-]+)',
        r'Product Code:\s*([A-Z0-9-]+)',
        r'Item Code:\s*([A-Z0-9-]+)',
        r'Code:\s*([A-Z0-9-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_barcode_from_text(text: str) -> str:
    """Extract barcode/EAN from text"""

    patterns = [
        r'EAN:\s*(\d{13})',
        r'Barcode:\s*(\d{8,14})',
        r'UPC:\s*(\d{12})',
        r'GTIN:\s*(\d{8,14})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_brand_from_text(text: str) -> str:
    """Extract brand from text"""

    patterns = [
        r'Brand:\s*(.+?)(?:\n|$)',
        r'Manufacturer:\s*(.+?)(?:\n|$)',
        r'Make:\s*(.+?)(?:\n|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_features_from_text(text: str) -> List[str]:
    """Extract features from text"""
    features = []

    # Look for Features section
    features_match = re.search(
        r'Features?:\s*(.+?)(?:\n\n|\Z)',
        text,
        re.IGNORECASE | re.DOTALL
    )

    if features_match:
        section = features_match.group(1)

        # Look for bullet points
        bullets = re.findall(r'[•●○\-\*]\s*(.+?)(?:\n|$)', section)
        if bullets:
            features.extend([b.strip() for b in bullets])
        else:
            # Split by newlines
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            features.extend(lines)

    # Look for standalone bullet points
    if not features:
        bullets = re.findall(r'[•●○]\s*(.+?)(?:\n|$)', text)
        features.extend([b.strip() for b in bullets if len(b.strip()) > 5])

    # Deduplicate and limit
    seen = set()
    unique = []
    for f in features:
        if f.lower() not in seen:
            seen.add(f.lower())
            unique.append(f)

    return unique[:10]


def extract_benefits_from_text(text: str) -> List[str]:
    """Extract benefits from text"""
    benefits = []

    # Look for Benefits section
    benefits_match = re.search(
        r'Benefits?:\s*(.+?)(?:\n\n|\Z)',
        text,
        re.IGNORECASE | re.DOTALL
    )

    if benefits_match:
        section = benefits_match.group(1)

        # Look for bullet points
        bullets = re.findall(r'[•●○\-\*]\s*(.+?)(?:\n|$)', section)
        if bullets:
            benefits.extend([b.strip() for b in bullets])
        else:
            # Split by newlines
            lines = [line.strip() for line in section.split('\n') if line.strip()]
            benefits.extend(lines)

    # Deduplicate and limit
    seen = set()
    unique = []
    for b in benefits:
        if b.lower() not in seen:
            seen.add(b.lower())
            unique.append(b)

    return unique[:10]


def extract_specs_from_text(text: str) -> Dict[str, Any]:
    """Extract specifications from text"""
    specs = {}

    # Common specification patterns
    spec_patterns = {
        'material': r'Material:\s*(.+?)(?:\n|$)',
        'dimensions': r'Dimensions?:\s*(.+?)(?:\n|$)',
        'weight': r'Weight:\s*(.+?)(?:\n|$)',
        'capacity': r'Capacity:\s*(.+?)(?:\n|$)',
        'powerW': r'Power:\s*(\d+)\s*W',
        'origin': r'(?:Made in|Origin):\s*(.+?)(?:\n|$)',
        'guarantee': r'(?:Guarantee|Warranty):\s*(.+?)(?:\n|$)',
        'care': r'Care:\s*(.+?)(?:\n|$)',
    }

    for key, pattern in spec_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            specs[key] = match.group(1).strip()

    # Look for Specifications section
    specs_match = re.search(
        r'Specifications?:\s*(.+?)(?:\n\n|\Z)',
        text,
        re.IGNORECASE | re.DOTALL
    )

    if specs_match:
        section = specs_match.group(1)

        # Look for key:value pairs
        pairs = re.findall(r'([A-Za-z\s]+):\s*([^\n]+)', section)
        for key, value in pairs:
            key_lower = key.strip().lower()

            if 'material' in key_lower:
                specs['material'] = value.strip()
            elif 'dimension' in key_lower or 'size' in key_lower:
                specs['dimensions'] = value.strip()
            elif 'weight' in key_lower:
                specs['weight'] = value.strip()
            elif 'capacity' in key_lower or 'volume' in key_lower:
                specs['capacity'] = value.strip()
            elif 'power' in key_lower or 'watt' in key_lower:
                specs['powerW'] = value.strip()
            elif 'origin' in key_lower or 'made' in key_lower:
                specs['origin'] = value.strip()
            elif 'guarantee' in key_lower or 'warranty' in key_lower:
                specs['guarantee'] = value.strip()
            elif 'care' in key_lower or 'cleaning' in key_lower:
                specs['care'] = value.strip()

    return specs


def extract_usage_from_text(text: str) -> str:
    """Extract usage information from text"""

    patterns = [
        r'Usage:\s*(.+?)(?:\n\n|\Z)',
        r'Use:\s*(.+?)(?:\n\n|\Z)',
        r'How to use:\s*(.+?)(?:\n\n|\Z)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            usage = match.group(1).strip()
            # Limit length
            if len(usage) > 500:
                usage = usage[:497] + "..."
            return usage

    return ""
