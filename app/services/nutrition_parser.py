"""
Nutrition Table Parser for EarthFare
Extracts and normalizes nutritional information from HTML tables and text
"""
import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# Standard UK nutrition label fields with regex patterns
NUTRITION_PATTERNS: List[Tuple[str, str, str]] = [
    # (field_key, display_label, regex_pattern)
    ("energy_kj", "Energy (kJ)", r"[Ee]nergy[:\s]*(\d+)\s*kJ"),
    ("energy_kcal", "Energy (kcal)", r"[Ee]nergy[:\s]*(\d+)\s*kcal"),
    ("fat", "Fat", r"[Ff]at[:\s]*([\d.]+)\s*g"),
    ("saturates", "of which saturates", r"(?:of which )?[Ss]aturate[sd]?[:\s]*([\d.]+)\s*g"),
    ("carbohydrates", "Carbohydrates", r"[Cc]arbohydrate[s]?[:\s]*([\d.]+)\s*g"),
    ("sugars", "of which sugars", r"(?:of which )?[Ss]ugars?[:\s]*([\d.]+)\s*g"),
    ("fibre", "Fibre", r"[Ff]ibre[:\s]*([\d.]+)\s*g"),
    ("protein", "Protein", r"[Pp]rotein[:\s]*([\d.]+)\s*g"),
    ("salt", "Salt", r"[Ss]alt[:\s]*([\d.]+)\s*g"),
    ("sodium", "Sodium", r"[Ss]odium[:\s]*([\d.]+)\s*(?:mg|g)"),
]

# Additional fields sometimes found
EXTENDED_NUTRITION_PATTERNS: List[Tuple[str, str, str]] = [
    ("polyunsaturates", "of which polyunsaturates", r"(?:of which )?[Pp]olyunsaturate[sd]?[:\s]*([\d.]+)\s*g"),
    ("monounsaturates", "of which monounsaturates", r"(?:of which )?[Mm]onounsaturate[sd]?[:\s]*([\d.]+)\s*g"),
    ("polyols", "of which polyols", r"(?:of which )?[Pp]olyols?[:\s]*([\d.]+)\s*g"),
    ("starch", "of which starch", r"(?:of which )?[Ss]tarch[:\s]*([\d.]+)\s*g"),
    ("omega_3", "Omega-3", r"[Oo]mega[\s-]?3[:\s]*([\d.]+)\s*g"),
    ("omega_6", "Omega-6", r"[Oo]mega[\s-]?6[:\s]*([\d.]+)\s*g"),
    ("vitamin_a", "Vitamin A", r"[Vv]itamin\s*A[:\s]*([\d.]+)\s*(?:µg|mcg|ug)"),
    ("vitamin_c", "Vitamin C", r"[Vv]itamin\s*C[:\s]*([\d.]+)\s*mg"),
    ("vitamin_d", "Vitamin D", r"[Vv]itamin\s*D[:\s]*([\d.]+)\s*(?:µg|mcg|ug)"),
    ("calcium", "Calcium", r"[Cc]alcium[:\s]*([\d.]+)\s*mg"),
    ("iron", "Iron", r"[Ii]ron[:\s]*([\d.]+)\s*mg"),
]


def parse_nutrition_from_html(html: str) -> Dict[str, str]:
    """
    Parse nutrition information from HTML content

    Args:
        html: HTML string containing nutrition table or text

    Returns:
        Dict with nutrition field keys and values
    """
    if not html:
        return {}

    # Try table parsing first
    soup = BeautifulSoup(html, 'html.parser')

    # Look for tables
    tables = soup.find_all('table')
    for table in tables:
        nutrition = parse_nutrition_table(table)
        if nutrition and len(nutrition) >= 3:  # At least 3 fields found
            return nutrition

    # Fall back to text extraction
    text = soup.get_text(separator=' ')
    return parse_nutrition_from_text(text)


def parse_nutrition_table(table) -> Dict[str, str]:
    """
    Parse nutrition from an HTML table element

    Args:
        table: BeautifulSoup table element

    Returns:
        Dict with nutrition values
    """
    nutrition = {}

    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)

            # Match against known patterns
            for field_key, display_label, pattern in NUTRITION_PATTERNS + EXTENDED_NUTRITION_PATTERNS:
                if re.search(field_key.replace('_', '[ _-]?'), label) or \
                   display_label.lower() in label:
                    # Extract numeric value
                    match = re.search(r'([\d.]+)', value)
                    if match:
                        nutrition[field_key] = match.group(1)
                        break

    return nutrition


def parse_nutrition_from_text(text: str) -> Dict[str, str]:
    """
    Parse nutrition information from plain text using regex

    Args:
        text: Plain text containing nutrition information

    Returns:
        Dict with nutrition field keys and values
    """
    nutrition = {}

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Try each pattern
    for field_key, display_label, pattern in NUTRITION_PATTERNS + EXTENDED_NUTRITION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            nutrition[field_key] = match.group(1)

    return nutrition


def format_nutrition_for_display(nutrition: Dict[str, str]) -> List[str]:
    """
    Format nutrition dict as display-ready list

    Args:
        nutrition: Dict with nutrition values

    Returns:
        List of formatted strings for display
    """
    lines = ["Typical Values", "Per 100g"]

    # Define display order and labels
    display_order = [
        ("energy_kj", "Energy", "kJ"),
        ("energy_kcal", "Energy", "kcal"),
        ("fat", "Fat", "g"),
        ("saturates", "of which saturates", "g"),
        ("carbohydrates", "Carbohydrates", "g"),
        ("sugars", "of which sugars", "g"),
        ("fibre", "Fibre", "g"),
        ("protein", "Protein", "g"),
        ("salt", "Salt", "g"),
    ]

    for field_key, label, unit in display_order:
        if field_key in nutrition:
            lines.append(f"{label}: {nutrition[field_key]}{unit}")

    return lines


def format_nutrition_for_shopify(nutrition: Dict[str, str]) -> List[str]:
    """
    Format nutrition as Shopify metafield list

    Args:
        nutrition: Dict with nutrition values

    Returns:
        List formatted for Shopify list metafield
    """
    if not nutrition:
        return []

    lines = []

    # Energy first
    if "energy_kcal" in nutrition:
        lines.append(f"Energy,{nutrition['energy_kcal']}kcal")
    elif "energy_kj" in nutrition:
        lines.append(f"Energy,{nutrition['energy_kj']}kJ")

    # Macros
    macro_fields = [
        ("fat", "Fat", "g"),
        ("saturates", "of which saturates", "g"),
        ("carbohydrates", "Carbohydrates", "g"),
        ("sugars", "of which sugars", "g"),
        ("fibre", "Fibre", "g"),
        ("protein", "Protein", "g"),
        ("salt", "Salt", "g"),
    ]

    for field_key, label, unit in macro_fields:
        if field_key in nutrition:
            lines.append(f"{label},{nutrition[field_key]}{unit}")

    return lines


def extract_serving_size(text: str) -> Optional[str]:
    """
    Extract serving size from text

    Args:
        text: Text containing serving information

    Returns:
        Serving size string or None
    """
    patterns = [
        r"[Ss]erving [Ss]ize[:\s]*([\d.]+\s*g)",
        r"[Pp]er [Ss]erving[:\s]*([\d.]+\s*g)",
        r"[Pp]ortion [Ss]ize[:\s]*([\d.]+\s*g)",
        r"(\d+)\s*(?:servings?|portions?) per (?:pack|container)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def calculate_per_serving(nutrition: Dict[str, str], serving_grams: float) -> Dict[str, str]:
    """
    Calculate nutrition per serving from per 100g values

    Args:
        nutrition: Dict with per-100g values
        serving_grams: Serving size in grams

    Returns:
        Dict with per-serving values
    """
    if serving_grams <= 0:
        return nutrition

    multiplier = serving_grams / 100.0
    per_serving = {}

    for key, value in nutrition.items():
        try:
            numeric = float(value)
            per_serving[key] = str(round(numeric * multiplier, 1))
        except (ValueError, TypeError):
            per_serving[key] = value

    return per_serving


def is_low_sugar(nutrition: Dict[str, str]) -> bool:
    """Check if product qualifies as low sugar (<=5g per 100g)"""
    try:
        sugars = float(nutrition.get("sugars", "999"))
        return sugars <= 5.0
    except (ValueError, TypeError):
        return False


def is_low_fat(nutrition: Dict[str, str]) -> bool:
    """Check if product qualifies as low fat (<=3g per 100g)"""
    try:
        fat = float(nutrition.get("fat", "999"))
        return fat <= 3.0
    except (ValueError, TypeError):
        return False


def is_high_protein(nutrition: Dict[str, str]) -> bool:
    """Check if product qualifies as high protein (>=20% energy from protein)"""
    try:
        protein = float(nutrition.get("protein", "0"))
        energy = float(nutrition.get("energy_kcal", "1"))
        protein_kcal = protein * 4  # 4 kcal per gram protein
        return (protein_kcal / energy) >= 0.20
    except (ValueError, TypeError, ZeroDivisionError):
        return False


def is_high_fibre(nutrition: Dict[str, str]) -> bool:
    """Check if product qualifies as high fibre (>=6g per 100g)"""
    try:
        fibre = float(nutrition.get("fibre", "0"))
        return fibre >= 6.0
    except (ValueError, TypeError):
        return False
