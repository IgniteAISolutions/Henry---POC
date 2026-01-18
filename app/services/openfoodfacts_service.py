"""
OpenFoodFacts API Service for Nutrition Data
Free, open-source food product database with barcode lookup

API Documentation: https://openfoodfacts.github.io/openfoodfacts-server/api/
"""
import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# OpenFoodFacts API base URL
OFF_API_BASE = "https://world.openfoodfacts.org/api/v2/product"

# Timeout for API requests (seconds)
REQUEST_TIMEOUT = 10

# Rate limiting - OpenFoodFacts requests max 100 req/min
RATE_LIMIT_DELAY = 0.6  # seconds between requests


async def fetch_nutrition_by_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    """
    Fetch nutrition data from OpenFoodFacts using barcode (EAN/UPC)

    Args:
        barcode: Product barcode (EAN-13, UPC-A, etc.)

    Returns:
        Dict with nutrition data per 100g, or None if not found

    Example return:
        {
            "energy_kcal": "250",
            "energy_kj": "1046",
            "fat": "12.5",
            "saturates": "7.2",
            "carbohydrates": "28.0",
            "sugars": "18.5",
            "fibre": "2.1",
            "protein": "5.8",
            "salt": "0.3",
            "source": "openfoodfacts",
            "product_name": "Product Name from OFF",
            "brands": "Brand Name"
        }
    """
    if not barcode:
        return None

    # Clean barcode - remove spaces, dashes
    barcode = str(barcode).strip().replace(" ", "").replace("-", "")

    # Validate barcode format (should be numeric, 8-14 digits)
    if not barcode.isdigit() or len(barcode) < 8 or len(barcode) > 14:
        logger.warning(f"Invalid barcode format: {barcode}")
        return None

    url = f"{OFF_API_BASE}/{barcode}.json"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": "Earthfare-ProductAutomation/1.0"}
            ) as response:

                if response.status == 404:
                    logger.info(f"Product not found in OpenFoodFacts: {barcode}")
                    return None

                if response.status != 200:
                    logger.warning(f"OpenFoodFacts API error {response.status} for barcode {barcode}")
                    return None

                data = await response.json()

                if data.get("status") != 1:
                    logger.info(f"Product not found in OpenFoodFacts: {barcode}")
                    return None

                product = data.get("product", {})
                nutriments = product.get("nutriments", {})

                if not nutriments:
                    logger.info(f"No nutrition data for barcode {barcode}")
                    return None

                # Extract nutrition per 100g
                nutrition = extract_nutrition_from_off(nutriments)

                # Add metadata
                nutrition["source"] = "openfoodfacts"
                nutrition["product_name"] = product.get("product_name", "")
                nutrition["brands"] = product.get("brands", "")
                nutrition["barcode"] = barcode

                # Add ingredients if available
                if product.get("ingredients_text"):
                    nutrition["ingredients_from_off"] = product.get("ingredients_text")

                # Add allergens if available
                allergens_tags = product.get("allergens_tags", [])
                if allergens_tags:
                    nutrition["allergens_from_off"] = [
                        tag.replace("en:", "").replace("-", " ").title()
                        for tag in allergens_tags
                    ]

                logger.info(f"Successfully fetched nutrition for barcode {barcode}")
                return nutrition

    except asyncio.TimeoutError:
        logger.warning(f"OpenFoodFacts request timeout for barcode {barcode}")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"OpenFoodFacts connection error for barcode {barcode}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching from OpenFoodFacts: {e}")
        return None


def extract_nutrition_from_off(nutriments: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract and normalize nutrition data from OpenFoodFacts nutriments object

    Args:
        nutriments: OpenFoodFacts nutriments dict

    Returns:
        Normalized nutrition dict with string values (per 100g)
    """
    nutrition = {}

    # Mapping from OpenFoodFacts keys to our standard keys
    # OFF uses _100g suffix for per-100g values
    field_mapping = {
        # Energy
        "energy-kcal_100g": "energy_kcal",
        "energy_100g": "energy_kj",  # OFF stores kJ as default energy

        # Macros
        "fat_100g": "fat",
        "saturated-fat_100g": "saturates",
        "carbohydrates_100g": "carbohydrates",
        "sugars_100g": "sugars",
        "fiber_100g": "fibre",
        "proteins_100g": "protein",
        "salt_100g": "salt",

        # Additional macros
        "monounsaturated-fat_100g": "monounsaturates",
        "polyunsaturated-fat_100g": "polyunsaturates",
        "trans-fat_100g": "trans_fat",
        "cholesterol_100g": "cholesterol",
        "starch_100g": "starch",
        "polyols_100g": "polyols",

        # Vitamins
        "vitamin-a_100g": "vitamin_a",
        "vitamin-c_100g": "vitamin_c",
        "vitamin-d_100g": "vitamin_d",
        "vitamin-e_100g": "vitamin_e",
        "vitamin-b1_100g": "vitamin_b1",
        "vitamin-b2_100g": "vitamin_b2",
        "vitamin-b6_100g": "vitamin_b6",
        "vitamin-b12_100g": "vitamin_b12",

        # Minerals
        "calcium_100g": "calcium",
        "iron_100g": "iron",
        "magnesium_100g": "magnesium",
        "zinc_100g": "zinc",
        "potassium_100g": "potassium",
        "sodium_100g": "sodium",

        # Omega fatty acids
        "omega-3-fat_100g": "omega_3",
        "omega-6-fat_100g": "omega_6",
    }

    for off_key, our_key in field_mapping.items():
        value = nutriments.get(off_key)
        if value is not None:
            # Format value - round to 1 decimal place for readability
            try:
                num_value = float(value)
                if num_value == int(num_value):
                    nutrition[our_key] = str(int(num_value))
                else:
                    nutrition[our_key] = f"{num_value:.1f}"
            except (ValueError, TypeError):
                nutrition[our_key] = str(value)

    # Handle energy specially - ensure we have both kJ and kcal
    if "energy_kj" in nutrition and "energy_kcal" not in nutrition:
        try:
            kj = float(nutrition["energy_kj"])
            kcal = kj / 4.184
            nutrition["energy_kcal"] = f"{kcal:.0f}"
        except (ValueError, TypeError):
            pass
    elif "energy_kcal" in nutrition and "energy_kj" not in nutrition:
        try:
            kcal = float(nutrition["energy_kcal"])
            kj = kcal * 4.184
            nutrition["energy_kj"] = f"{kj:.0f}"
        except (ValueError, TypeError):
            pass

    return nutrition


async def fetch_nutrition_batch(barcodes: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Fetch nutrition for multiple barcodes with rate limiting

    Args:
        barcodes: List of barcodes to lookup

    Returns:
        Dict mapping barcode -> nutrition data (or None if not found)
    """
    results = {}

    for i, barcode in enumerate(barcodes):
        if i > 0:
            # Rate limiting delay
            await asyncio.sleep(RATE_LIMIT_DELAY)

        results[barcode] = await fetch_nutrition_by_barcode(barcode)

        # Log progress for large batches
        if (i + 1) % 10 == 0:
            logger.info(f"Processed {i + 1}/{len(barcodes)} barcodes")

    return results


def format_off_nutrition_for_display(nutrition: Dict[str, str]) -> List[str]:
    """
    Format OpenFoodFacts nutrition data for human-readable display

    Args:
        nutrition: Nutrition dict from fetch_nutrition_by_barcode

    Returns:
        List of formatted strings like ["Energy: 250kcal", "Fat: 12.5g", ...]
    """
    if not nutrition:
        return []

    lines = []

    # Define display order and units
    display_fields = [
        ("energy_kcal", "Energy", "kcal"),
        ("energy_kj", "Energy", "kJ"),
        ("fat", "Fat", "g"),
        ("saturates", "of which saturates", "g"),
        ("carbohydrates", "Carbohydrates", "g"),
        ("sugars", "of which sugars", "g"),
        ("fibre", "Fibre", "g"),
        ("protein", "Protein", "g"),
        ("salt", "Salt", "g"),
    ]

    for key, label, unit in display_fields:
        if key in nutrition and nutrition[key]:
            value = nutrition[key]
            # Skip duplicate energy if we have both
            if key == "energy_kj" and "energy_kcal" in nutrition:
                continue
            lines.append(f"{label}: {value}{unit}")

    return lines


def format_off_nutrition_for_shopify(nutrition: Dict[str, str]) -> List[str]:
    """
    Format OpenFoodFacts nutrition for Shopify list metafield

    Args:
        nutrition: Nutrition dict from fetch_nutrition_by_barcode

    Returns:
        List suitable for Shopify list.single_line_text_field metafield
    """
    if not nutrition:
        return []

    lines = []

    # Core nutrition fields in standard UK label order
    fields = [
        ("energy_kj", "Energy", "kJ"),
        ("energy_kcal", "", "kcal"),  # Combined with kJ
        ("fat", "Fat", "g"),
        ("saturates", "of which saturates", "g"),
        ("monounsaturates", "of which mono-unsaturates", "g"),
        ("polyunsaturates", "of which polyunsaturates", "g"),
        ("carbohydrates", "Carbohydrate", "g"),
        ("sugars", "of which sugars", "g"),
        ("polyols", "of which polyols", "g"),
        ("starch", "of which starch", "g"),
        ("fibre", "Fibre", "g"),
        ("protein", "Protein", "g"),
        ("salt", "Salt", "g"),
    ]

    # Handle energy specially - combine kJ and kcal
    energy_kj = nutrition.get("energy_kj", "")
    energy_kcal = nutrition.get("energy_kcal", "")
    if energy_kj and energy_kcal:
        lines.append(f"Energy: {energy_kj}kJ / {energy_kcal}kcal")
    elif energy_kcal:
        lines.append(f"Energy: {energy_kcal}kcal")
    elif energy_kj:
        lines.append(f"Energy: {energy_kj}kJ")

    # Add other fields
    for key, label, unit in fields:
        if key.startswith("energy"):
            continue  # Already handled
        if key in nutrition and nutrition[key]:
            value = nutrition[key]
            lines.append(f"{label}: {value}{unit}")

    return lines
