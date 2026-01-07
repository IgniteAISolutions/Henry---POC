"""
Dietary Attribute Detector for EarthFare
Detects dietary preferences from ingredients, product text, and badges

This module derives dietary attributes like Vegan, Gluten Free, etc.
from ingredient lists - not just from explicit labels.
"""
import re
from typing import List, Dict, Set, Optional
import logging

logger = logging.getLogger(__name__)

# Dietary detection rules
# negative_ingredients: If ANY of these are present, product is NOT this attribute
# positive_markers: Explicit labels that confirm the attribute
# requires_explicit_marker: True if we can't derive from ingredients (e.g., Organic)

DIETARY_RULES: Dict[str, Dict] = {
    "Gluten Free": {
        "negative_ingredients": [
            "wheat", "barley", "rye", "oats", "spelt", "kamut", "triticale",
            "semolina", "durum", "bulgur", "couscous", "farina", "farro",
            "gluten", "seitan", "malt", "brewer's yeast"
        ],
        "positive_markers": ["gluten free", "gluten-free", "gf", "coeliac friendly", "celiac friendly"],
        "requires_explicit_marker": False,
        "check_certification": True
    },
    "Vegan": {
        "negative_ingredients": [
            # Dairy
            "milk", "dairy", "cream", "butter", "cheese", "whey", "casein",
            "lactose", "ghee", "yoghurt", "yogurt", "curd", "buttermilk",
            # Eggs
            "egg", "albumen", "albumin", "mayonnaise", "meringue",
            # Meat/Fish
            "meat", "beef", "pork", "chicken", "fish", "seafood", "anchovy",
            "prawn", "shrimp", "crab", "lobster", "bacon", "ham", "lard",
            "tallow", "suet", "gelatin", "gelatine", "collagen",
            # Other animal products
            "honey", "beeswax", "royal jelly", "propolis",
            "shellac", "carmine", "cochineal", "isinglass",
            "lanolin", "keratin", "silk", "wool"
        ],
        "positive_markers": ["vegan", "plant-based", "plant based", "100% plant", "no animal"],
        "requires_explicit_marker": False,
        "check_certification": True
    },
    "Vegetarian": {
        "negative_ingredients": [
            # Meat/Fish (but NOT dairy/eggs)
            "meat", "beef", "pork", "chicken", "fish", "seafood", "anchovy",
            "prawn", "shrimp", "crab", "lobster", "bacon", "ham", "lard",
            "tallow", "suet", "gelatin", "gelatine", "collagen", "isinglass"
        ],
        "positive_markers": ["vegetarian", "veggie", "meat free", "meat-free"],
        "requires_explicit_marker": False,
        "check_certification": True
    },
    "Dairy Free": {
        "negative_ingredients": [
            "milk", "dairy", "cream", "butter", "cheese", "whey", "casein",
            "lactose", "ghee", "yoghurt", "yogurt", "curd", "buttermilk",
            "milk powder", "skimmed milk", "whole milk", "condensed milk",
            "evaporated milk", "milk solids", "milk protein", "cream cheese",
            "sour cream", "ice cream", "fromage", "quark"
        ],
        "positive_markers": ["dairy free", "dairy-free", "lactose free", "lactose-free", "milk free"],
        "requires_explicit_marker": False,
        "check_certification": True
    },
    "Nut Free": {
        "negative_ingredients": [
            "almond", "hazelnut", "walnut", "cashew", "pistachio", "pecan",
            "brazil nut", "macadamia", "chestnut", "pine nut", "praline",
            "marzipan", "frangipane", "nougat", "nut butter", "nut oil",
            "peanut"  # Technically a legume but often grouped with nuts
        ],
        "positive_markers": ["nut free", "nut-free", "tree nut free", "peanut free"],
        "requires_explicit_marker": False,
        "check_certification": True
    },
    "Sugar Free": {
        "negative_ingredients": [
            "sugar", "sucrose", "glucose", "fructose", "dextrose",
            "maltose", "lactose", "galactose", "trehalose",
            "brown sugar", "cane sugar", "beet sugar", "raw sugar",
            "icing sugar", "powdered sugar", "caster sugar", "demerara",
            "muscovado", "molasses", "treacle", "golden syrup",
            "maple syrup", "agave", "honey", "corn syrup",
            "high fructose corn syrup", "hfcs", "invert sugar"
        ],
        "positive_markers": ["sugar free", "sugar-free", "no added sugar", "unsweetened", "zero sugar"],
        "requires_explicit_marker": False,  # Can derive if no sugars in ingredients
        "check_certification": False
    },
    "Seed Oil Free": {
        "negative_ingredients": [
            "sunflower oil", "rapeseed oil", "canola oil", "vegetable oil",
            "soybean oil", "soya oil", "corn oil", "cottonseed oil",
            "safflower oil", "grapeseed oil", "rice bran oil",
            "palm oil", "palm kernel oil"  # Often grouped with seed oils
        ],
        "positive_markers": ["seed oil free", "no seed oils"],
        "requires_explicit_marker": False,
        "check_certification": False
    },
    "Palm Oil Free": {
        "negative_ingredients": [
            "palm oil", "palm kernel oil", "palm fat", "palmitate",
            "palmate", "palm stearin", "palm olein", "glyceryl stearate",
            "stearic acid", "sodium laureth sulfate", "sodium lauryl sulfate"
        ],
        "positive_markers": ["palm oil free", "palm-free", "no palm oil"],
        "requires_explicit_marker": False,
        "check_certification": False
    },
    "Organic": {
        # Cannot derive from ingredients - MUST have explicit certification
        "negative_ingredients": [],
        "positive_markers": [
            "organic", "certified organic", "soil association", "of certified organic"
        ],
        "requires_explicit_marker": True,
        "check_certification": True
    },
    "Fairtrade": {
        "negative_ingredients": [],
        "positive_markers": ["fairtrade", "fair trade", "fairly traded"],
        "requires_explicit_marker": True,
        "check_certification": True
    },
    "Raw": {
        "negative_ingredients": [],
        "positive_markers": ["raw", "unroasted", "uncooked", "cold pressed"],
        "requires_explicit_marker": True,
        "check_certification": False
    },
    "Keto": {
        # Low carb, high fat
        "negative_ingredients": [
            "sugar", "flour", "wheat", "rice", "potato", "corn starch",
            "bread", "pasta", "cereal", "oats"
        ],
        "positive_markers": ["keto", "keto friendly", "keto-friendly", "low carb"],
        "requires_explicit_marker": False,
        "check_certification": False
    },
    "Paleo": {
        "negative_ingredients": [
            "dairy", "milk", "cheese", "wheat", "grain", "legume", "bean",
            "lentil", "peanut", "soy", "corn", "potato", "sugar", "refined"
        ],
        "positive_markers": ["paleo", "paleo friendly", "paleo-friendly"],
        "requires_explicit_marker": False,
        "check_certification": False
    }
}

# Allergen patterns for extraction
ALLERGEN_PATTERNS = {
    "celery": ["celery", "celeriac"],
    "cereals_containing_gluten": ["wheat", "rye", "barley", "oats", "spelt", "kamut"],
    "crustaceans": ["crab", "lobster", "prawn", "shrimp", "crayfish", "langoustine"],
    "eggs": ["egg", "albumen", "albumin"],
    "fish": ["fish", "cod", "salmon", "tuna", "anchovy", "sardine", "mackerel"],
    "lupin": ["lupin", "lupine"],
    "milk": ["milk", "cream", "butter", "cheese", "whey", "casein", "lactose", "yoghurt"],
    "molluscs": ["mussel", "oyster", "squid", "octopus", "clam", "scallop", "snail"],
    "mustard": ["mustard"],
    "nuts": ["almond", "hazelnut", "walnut", "cashew", "pistachio", "pecan", "brazil nut", "macadamia"],
    "peanuts": ["peanut", "groundnut", "arachis"],
    "sesame": ["sesame", "tahini"],
    "soya": ["soya", "soy", "edamame", "tofu", "tempeh"],
    "sulphites": ["sulphite", "sulfite", "sulphur dioxide", "e220", "e221", "e222", "e223", "e224", "e225", "e226", "e227", "e228"]
}


def detect_dietary_attributes(
    ingredients: str,
    product_text: str = "",
    badges: List[str] = None,
    nutrition: Dict[str, str] = None
) -> List[str]:
    """
    Detect dietary attributes from ingredients and product data

    Args:
        ingredients: Ingredient list as string
        product_text: Additional product text (description, features)
        badges: List of badges/certifications from product page
        nutrition: Nutrition data dict (for keto/low-sugar detection)

    Returns:
        List of dietary attribute strings (e.g., ["Vegan", "Gluten Free"])
    """
    attributes = []
    ingredients_lower = ingredients.lower() if ingredients else ""
    product_lower = product_text.lower() if product_text else ""
    badges_text = " ".join(badges or []).lower()
    all_text = f"{ingredients_lower} {product_lower} {badges_text}"

    for attr_name, rules in DIETARY_RULES.items():
        # Check for explicit positive markers first
        has_marker = any(
            marker in all_text
            for marker in rules["positive_markers"]
        )

        # If requires explicit marker, only add if found
        if rules.get("requires_explicit_marker"):
            if has_marker:
                attributes.append(attr_name)
            continue

        # Check negative ingredients (if ANY present, product is NOT this attribute)
        has_negative = any(
            _ingredient_present(neg, ingredients_lower)
            for neg in rules["negative_ingredients"]
        )

        # Add attribute if:
        # 1. Has explicit marker, OR
        # 2. No negative ingredients found (and has ingredient list to check)
        if has_marker:
            attributes.append(attr_name)
        elif not has_negative and ingredients_lower and rules["negative_ingredients"]:
            # Only infer if we have ingredients to check against
            attributes.append(attr_name)

    # Additional nutrition-based detection
    if nutrition:
        # Low Sugar detection from nutrition facts
        if "Sugar Free" not in attributes:
            try:
                sugars = float(nutrition.get("sugars", "999"))
                if sugars <= 0.5:  # Less than 0.5g per 100g
                    attributes.append("Sugar Free")
            except (ValueError, TypeError):
                pass

    return sorted(set(attributes))


def _ingredient_present(ingredient: str, ingredients_text: str) -> bool:
    """
    Check if an ingredient is present, with word boundary awareness

    Args:
        ingredient: Ingredient to check for
        ingredients_text: Full ingredient list text (lowercase)

    Returns:
        True if ingredient is found
    """
    # Use word boundary to avoid partial matches
    # e.g., "oat" shouldn't match in "coated"
    pattern = r'\b' + re.escape(ingredient) + r'\b'
    return bool(re.search(pattern, ingredients_text))


def extract_allergens(ingredients: str) -> List[str]:
    """
    Extract allergen information from ingredients

    Args:
        ingredients: Ingredient list as string

    Returns:
        List of allergen names found
    """
    found_allergens = []
    ingredients_lower = ingredients.lower() if ingredients else ""

    for allergen_name, patterns in ALLERGEN_PATTERNS.items():
        for pattern in patterns:
            if _ingredient_present(pattern, ingredients_lower):
                # Use display-friendly name
                display_name = allergen_name.replace("_", " ").title()
                if display_name not in found_allergens:
                    found_allergens.append(display_name)
                break

    return sorted(found_allergens)


def parse_allergen_statement(text: str) -> Dict[str, List[str]]:
    """
    Parse "Contains: X, Y, Z" and "May contain: A, B" statements

    Args:
        text: Text containing allergen statements

    Returns:
        Dict with 'contains' and 'may_contain' lists
    """
    result = {
        "contains": [],
        "may_contain": []
    }

    text_lower = text.lower()

    # Parse "Contains:" statement
    contains_match = re.search(
        r'contains[:\s]+([^.]+?)(?:\.|may contain|$)',
        text_lower, re.IGNORECASE
    )
    if contains_match:
        items = contains_match.group(1)
        result["contains"] = [
            item.strip().title()
            for item in re.split(r'[,;&]', items)
            if item.strip()
        ]

    # Parse "May contain:" statement
    may_match = re.search(
        r'may contain[:\s]+([^.]+?)(?:\.|$)',
        text_lower, re.IGNORECASE
    )
    if may_match:
        items = may_match.group(1)
        result["may_contain"] = [
            item.strip().title()
            for item in re.split(r'[,;&]', items)
            if item.strip()
        ]

    return result


def parse_ingredients_list(ingredients_text: str) -> List[str]:
    """
    Parse comma-separated ingredients into a normalized list

    Args:
        ingredients_text: Raw ingredient string

    Returns:
        List of individual ingredients
    """
    if not ingredients_text:
        return []

    # Remove common prefixes
    text = re.sub(r'^ingredients?[:\s]*', '', ingredients_text, flags=re.IGNORECASE)

    # Split by comma, semicolon, or bullet points
    items = re.split(r'[,;•·]', text)

    # Clean each ingredient
    cleaned = []
    for item in items:
        # Remove percentages like "(5%)"
        item = re.sub(r'\([^)]*%[^)]*\)', '', item)
        # Remove asterisks and footnote markers
        item = re.sub(r'[*†‡§¹²³]+', '', item)
        # Clean whitespace
        item = item.strip()

        if item and len(item) > 1:
            cleaned.append(item)

    return cleaned


def get_dietary_summary(attributes: List[str]) -> str:
    """
    Generate a human-readable dietary summary

    Args:
        attributes: List of dietary attributes

    Returns:
        Summary string for display
    """
    if not attributes:
        return ""

    # Priority order for display
    priority = [
        "Organic", "Vegan", "Vegetarian", "Gluten Free",
        "Dairy Free", "Nut Free", "Sugar Free", "Fairtrade"
    ]

    # Sort by priority, then alphabetically for others
    sorted_attrs = sorted(
        attributes,
        key=lambda x: (priority.index(x) if x in priority else 999, x)
    )

    return ". ".join(sorted_attrs) + "."
