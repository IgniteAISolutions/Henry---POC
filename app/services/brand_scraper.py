"""
Brand Website Scraper for EarthFare
Scrapes manufacturer websites directly for product data when OpenFoodFacts fails.

Supports:
- Clearspring (clearspring.co.uk)
- Generic brand website scraping
"""
import asyncio
import aiohttp
import logging
import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus

logger = logging.getLogger(__name__)

# Request timeout
REQUEST_TIMEOUT = 15

# User agent for requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Brand-specific configurations
BRAND_CONFIGS = {
    "clearspring": {
        "base_url": "https://www.clearspring.co.uk",
        "search_url": "https://www.clearspring.co.uk/search?q={query}",
        "selectors": {
            "product_link": ".product-item a, .product-card a, .grid-product a",
            "name": "h1.product-title, h1.product__title, .product-single__title",
            "ingredients": ".ingredients, #ingredients, [class*='ingredient'], .product-description:contains('Ingredients')",
            "nutrition": ".nutrition, #nutrition, .nutritional-info, table.nutrition-table",
            "description": ".product-description, .product__description, [itemprop='description']",
            "allergens": ".allergens, .allergy-info, [class*='allergen']",
        }
    },
    "suma": {
        "base_url": "https://www.suma.coop",
        "search_url": "https://www.suma.coop/search/?q={query}",
        "selectors": {
            "product_link": ".product-item a",
            "name": "h1.product-title",
            "ingredients": ".ingredients",
            "nutrition": ".nutrition-table",
            "description": ".product-description",
        }
    },
    "essential": {
        "base_url": "https://www.essentialtrading.coop",
        "search_url": "https://www.essentialtrading.coop/search?q={query}",
        "selectors": {
            "product_link": ".product-item a",
            "name": "h1",
            "ingredients": ".ingredients",
            "nutrition": ".nutrition",
            "description": ".description",
        }
    }
}


async def scrape_brand_website(
    brand: str,
    product_name: str,
    barcode: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Scrape a brand's website for product data.

    Args:
        brand: Brand name (e.g., "Clearspring")
        product_name: Product name for search
        barcode: Optional barcode for more precise search

    Returns:
        Dict with ingredients, nutrition, description, or None if not found
    """
    # Normalize brand name
    brand_key = brand.lower().strip()

    # Find matching config
    config = None
    for key, cfg in BRAND_CONFIGS.items():
        if key in brand_key or brand_key in key:
            config = cfg
            brand_key = key
            break

    if not config:
        logger.debug(f"No scraper config for brand: {brand}")
        return None

    logger.info(f"🌐 Scraping {brand} website for: {product_name}")

    try:
        # Build search query
        search_query = barcode if barcode else product_name
        search_url = config["search_url"].format(query=quote_plus(search_query))

        # Fetch search results
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": USER_AGENT}

            # Step 1: Search for product
            async with session.get(
                search_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Search failed with status {response.status}")
                    return None

                search_html = await response.text()

            # Parse search results
            soup = BeautifulSoup(search_html, 'html.parser')

            # Find product links
            product_url = None
            for selector in config["selectors"]["product_link"].split(", "):
                links = soup.select(selector)
                for link in links:
                    href = link.get("href", "")
                    link_text = link.get_text(strip=True).lower()
                    product_lower = product_name.lower()

                    # Check if this link matches our product
                    # Match on key words from product name
                    keywords = [w for w in product_lower.split() if len(w) > 3]
                    if any(kw in link_text or kw in href.lower() for kw in keywords):
                        product_url = urljoin(config["base_url"], href)
                        break
                if product_url:
                    break

            if not product_url:
                logger.info(f"No product found on {brand} website for: {product_name}")
                return None

            logger.info(f"Found product page: {product_url}")

            # Step 2: Fetch product page
            async with session.get(
                product_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Product page fetch failed: {response.status}")
                    return None

                product_html = await response.text()

            # Parse product page
            return parse_product_page(product_html, config["selectors"], product_url)

    except asyncio.TimeoutError:
        logger.warning(f"Timeout scraping {brand} website")
        return None
    except aiohttp.ClientError as e:
        logger.warning(f"Network error scraping {brand}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error scraping {brand}: {e}")
        return None


def parse_product_page(html: str, selectors: Dict[str, str], source_url: str) -> Dict[str, Any]:
    """
    Parse a product page HTML and extract data.

    Args:
        html: Product page HTML
        selectors: CSS selectors for data extraction
        source_url: URL of the page (for source tracking)

    Returns:
        Dict with extracted product data
    """
    soup = BeautifulSoup(html, 'html.parser')
    data = {
        "source_url": source_url,
        "source": "brand_website"
    }

    # Extract name
    for selector in selectors.get("name", "").split(", "):
        element = soup.select_one(selector)
        if element:
            data["name"] = element.get_text(strip=True)
            break

    # Extract ingredients - try multiple methods
    ingredients = extract_ingredients_from_html(soup, selectors.get("ingredients", ""))
    if ingredients:
        data["ingredients"] = ingredients

    # Extract nutrition
    nutrition = extract_nutrition_from_html(soup, selectors.get("nutrition", ""))
    if nutrition:
        data["nutrition"] = nutrition

    # Extract description
    for selector in selectors.get("description", "").split(", "):
        element = soup.select_one(selector)
        if element:
            data["description"] = element.get_text(strip=True)
            break

    # Extract allergens
    allergens = extract_allergens_from_html(soup, selectors.get("allergens", ""))
    if allergens:
        data["allergens"] = allergens

    # Log what was found
    found = [k for k in ["ingredients", "nutrition", "description", "allergens"] if data.get(k)]
    logger.info(f"✅ Extracted from brand website: {', '.join(found) if found else 'nothing'}")

    return data


def extract_ingredients_from_html(soup: BeautifulSoup, selector: str) -> str:
    """Extract ingredients from HTML using multiple strategies."""

    # Strategy 1: Try CSS selectors
    for sel in selector.split(", "):
        element = soup.select_one(sel)
        if element:
            text = element.get_text(strip=True)
            if len(text) > 10:
                return clean_ingredients_text(text)

    # Strategy 2: Look for "Ingredients:" label in text
    page_text = soup.get_text()
    patterns = [
        r'Ingredients?\s*[:\-]\s*(.+?)(?=\n\s*(?:Nutrition|Allergen|Storage|Warning|$))',
        r'Ingredients?\s*[:\-]\s*(.+?)(?=\.|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE | re.DOTALL)
        if match:
            ingredients = match.group(1).strip()
            if len(ingredients) > 10:
                return clean_ingredients_text(ingredients)

    # Strategy 3: Look for common ingredient container classes
    for class_hint in ['ingredient', 'composition', 'contents']:
        elements = soup.find_all(class_=re.compile(class_hint, re.I))
        for element in elements:
            text = element.get_text(strip=True)
            if len(text) > 10 and ',' in text:  # Ingredients usually have commas
                return clean_ingredients_text(text)

    return ""


def clean_ingredients_text(text: str) -> str:
    """Clean up extracted ingredients text."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove "Ingredients:" prefix if present
    text = re.sub(r'^Ingredients?\s*[:\-]\s*', '', text, flags=re.I)
    return text.strip()


def extract_nutrition_from_html(soup: BeautifulSoup, selector: str) -> Dict[str, str]:
    """Extract nutrition data from HTML."""
    nutrition = {}

    # Try to find nutrition table
    tables = soup.find_all('table')
    for table in tables:
        table_text = table.get_text().lower()
        if any(kw in table_text for kw in ['energy', 'calories', 'protein', 'fat', 'carbohydrate']):
            # Parse nutrition table
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)

                    # Map to standard keys
                    if 'energy' in label and 'kcal' in label:
                        nutrition['energy_kcal'] = extract_numeric(value)
                    elif 'energy' in label and 'kj' in label:
                        nutrition['energy_kj'] = extract_numeric(value)
                    elif 'fat' in label and 'saturate' not in label:
                        nutrition['fat'] = extract_numeric(value)
                    elif 'saturate' in label:
                        nutrition['saturates'] = extract_numeric(value)
                    elif 'carbohydrate' in label and 'sugar' not in label:
                        nutrition['carbohydrates'] = extract_numeric(value)
                    elif 'sugar' in label:
                        nutrition['sugars'] = extract_numeric(value)
                    elif 'fibre' in label or 'fiber' in label:
                        nutrition['fibre'] = extract_numeric(value)
                    elif 'protein' in label:
                        nutrition['protein'] = extract_numeric(value)
                    elif 'salt' in label or 'sodium' in label:
                        nutrition['salt'] = extract_numeric(value)

            if nutrition:
                return nutrition

    # Try text-based extraction as fallback
    page_text = soup.get_text()
    patterns = {
        'energy_kcal': r'(?:energy|calories?)[:\s]*(\d+)\s*(?:kcal|cal)',
        'fat': r'fat[:\s]*(\d+\.?\d*)\s*g',
        'protein': r'protein[:\s]*(\d+\.?\d*)\s*g',
        'carbohydrates': r'carbohydrate[s]?[:\s]*(\d+\.?\d*)\s*g',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, page_text, re.I)
        if match:
            nutrition[key] = match.group(1)

    return nutrition


def extract_numeric(value: str) -> str:
    """Extract numeric value from string like '12.5g' or '250 kcal'."""
    match = re.search(r'(\d+\.?\d*)', value)
    return match.group(1) if match else ""


def extract_allergens_from_html(soup: BeautifulSoup, selector: str) -> List[str]:
    """Extract allergens from HTML."""
    allergens = []

    # Common allergens to look for
    common_allergens = [
        'milk', 'egg', 'peanut', 'tree nut', 'soy', 'soya', 'wheat', 'gluten',
        'fish', 'shellfish', 'sesame', 'celery', 'mustard', 'lupin', 'mollusc'
    ]

    # Try selector first
    for sel in selector.split(", "):
        element = soup.select_one(sel)
        if element:
            text = element.get_text().lower()
            for allergen in common_allergens:
                if allergen in text:
                    allergens.append(allergen.title())

    # Also look for bold text in ingredients (common for allergens)
    bold_elements = soup.find_all(['strong', 'b'])
    for element in bold_elements:
        text = element.get_text().lower()
        for allergen in common_allergens:
            if allergen in text and allergen.title() not in allergens:
                allergens.append(allergen.title())

    return allergens


async def scrape_multiple_products(
    brand: str,
    products: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Scrape brand website for multiple products.

    Args:
        brand: Brand name
        products: List of product dicts with name and optional barcode

    Returns:
        List of scraped data dicts (same order as input)
    """
    results = []

    for i, product in enumerate(products):
        name = product.get("name", "")
        barcode = product.get("barcode", "") or product.get("ean", "")

        logger.info(f"Scraping {i+1}/{len(products)}: {name}")

        try:
            data = await scrape_brand_website(brand, name, barcode)
            results.append(data or {})
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {e}")
            results.append({})

        # Rate limiting - be respectful
        if i < len(products) - 1:
            await asyncio.sleep(1)

    return results
