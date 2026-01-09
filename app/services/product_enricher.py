"""
Product Enricher for EarthFare
Enriches product data by scraping supplier websites for ingredients,
nutrition, and dietary information.

Integrates:
- FireCrawl API for intelligent scraping (primary)
- Supplier-specific scraping (fallback)
- Nutrition parsing
- Dietary attribute detection from ingredients
- Allergen extraction
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup

from ..config.suppliers import (
    SUPPLIER_CONFIGS,
    SOURCE_WEIGHTS,
    FALLBACK_SEARCH_URLS,
    get_brand_website,
    slugify
)
from .nutrition_parser import (
    parse_nutrition_from_html,
    format_nutrition_for_shopify
)
from .dietary_detector import (
    detect_dietary_attributes,
    extract_allergens,
    parse_ingredients_list,
    parse_allergen_statement
)

logger = logging.getLogger(__name__)

# Import FireCrawl service (primary scraper)
try:
    from .firecrawl_service import (
        is_firecrawl_configured,
        extract_product_data as firecrawl_extract,
        scrape_supplier_product,
        discover_page_selectors
    )
    HAS_FIRECRAWL = True
except ImportError:
    HAS_FIRECRAWL = False
    logger.warning("FireCrawl service not available")

# Import existing scraper (fallback)
try:
    from .url_scraper import scrape_url
    HAS_URL_SCRAPER = True
except ImportError:
    HAS_URL_SCRAPER = False
    logger.warning("url_scraper not available - limited scraping capability")


async def enrich_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a single product with scraped data from suppliers

    Args:
        product: Product dict with at least name, and optionally ean/barcode/brand

    Returns:
        Enriched product dict with ingredients, nutrition, dietary info
    """
    ean = product.get("ean") or product.get("barcode") or product.get("Variant Barcode", "")
    name = product.get("name") or product.get("Title") or product.get("product_name", "")
    brand = product.get("brand") or product.get("Vendor", "")

    logger.info(f"Enriching product: {name} (EAN: {ean})")

    # Scrape from multiple sources
    scraped_data = await scrape_product_data(ean, name, brand)

    # Parse nutrition from scraped HTML
    nutrition = {}
    if scraped_data.get("nutrition_html"):
        nutrition = parse_nutrition_from_html(scraped_data["nutrition_html"])

    # Get ingredients
    ingredients_text = scraped_data.get("ingredients", "") or product.get("ingredients", "")
    ingredients_list = parse_ingredients_list(ingredients_text)

    # Detect dietary attributes from ingredients
    dietary = detect_dietary_attributes(
        ingredients=ingredients_text,
        product_text=scraped_data.get("description", ""),
        badges=scraped_data.get("dietary_badges", []),
        nutrition=nutrition
    )

    # Extract allergens
    allergens = extract_allergens(ingredients_text)

    # Parse any "Contains:" statements
    allergen_statement = parse_allergen_statement(
        scraped_data.get("allergen_text", "") or ingredients_text
    )
    if allergen_statement.get("contains"):
        for a in allergen_statement["contains"]:
            if a not in allergens:
                allergens.append(a)

    # Merge with original product
    enriched = {
        **product,
        "ingredients": ingredients_text,
        "ingredients_list": ingredients_list,
        "nutrition": nutrition,
        "nutrition_shopify": format_nutrition_for_shopify(nutrition),
        "dietary": dietary,
        "dietary_preferences": dietary,  # Alias for Shopify export
        "allergens": allergens,
        "may_contain": allergen_statement.get("may_contain", []),
        "description_scraped": scraped_data.get("description", ""),
        "_scrape_sources": scraped_data.get("_sources", [])
    }

    logger.info(f"Enriched {name}: {len(dietary)} dietary tags, {len(allergens)} allergens")

    return enriched


async def enrich_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich multiple products

    Args:
        products: List of product dicts

    Returns:
        List of enriched product dicts
    """
    enriched = []
    for i, product in enumerate(products):
        logger.info(f"Processing product {i+1}/{len(products)}")
        try:
            enriched_product = await enrich_product(product)
            enriched.append(enriched_product)
        except Exception as e:
            logger.error(f"Failed to enrich product {product.get('name', 'unknown')}: {e}")
            product["_enrichment_error"] = str(e)
            enriched.append(product)

        # Small delay between requests to be respectful
        await asyncio.sleep(0.5)

    return enriched


async def scrape_product_data(
    ean: str,
    product_name: str,
    brand: str = ""
) -> Dict[str, Any]:
    """
    Scrape product data from multiple sources, weighted by quality.
    Uses FireCrawl API as primary method, falls back to direct scraping.

    Args:
        ean: Product EAN/barcode
        product_name: Product name for search
        brand: Brand name for website lookup

    Returns:
        Combined scraped data from best sources
    """
    results = []

    # PRIMARY: Try FireCrawl if configured (handles anti-bot, JS rendering)
    if HAS_FIRECRAWL and is_firecrawl_configured():
        logger.info("Using FireCrawl for product scraping")

        # 1. Try brand website first via FireCrawl
        if brand:
            brand_url = get_brand_website(brand)
            if brand_url:
                try:
                    search_url = f"{brand_url}/search?q={ean or slugify(product_name)}"
                    data = await firecrawl_extract(search_url)
                    if data and (data.get("ingredients") or data.get("product_name")):
                        # Convert FireCrawl format to our format
                        normalized = normalize_firecrawl_result(data)
                        normalized["source"] = "manufacturer"
                        normalized["weight"] = SOURCE_WEIGHTS["manufacturer"]
                        results.append(normalized)
                        logger.info(f"Got data from brand website: {brand_url}")
                except Exception as e:
                    logger.debug(f"FireCrawl brand scrape failed: {e}")

        # 2. Try suppliers via FireCrawl
        for supplier_key, config in SUPPLIER_CONFIGS.items():
            try:
                data = await scrape_supplier_product(
                    config["base_url"],
                    ean=ean,
                    product_name=product_name
                )
                if data and (data.get("ingredients") or data.get("product_name")):
                    normalized = normalize_firecrawl_result(data)
                    normalized["source"] = supplier_key
                    normalized["weight"] = SOURCE_WEIGHTS["big4_supplier"]
                    results.append(normalized)
                    logger.info(f"Got data from {supplier_key}")
                    break  # Stop after first successful supplier
            except Exception as e:
                logger.debug(f"FireCrawl {supplier_key} scrape failed: {e}")

        # 3. Try fallback searches via FireCrawl
        if not results or not any(r.get("ingredients") for r in results):
            query = ean if ean else product_name
            for source_name, url_pattern in FALLBACK_SEARCH_URLS[:2]:
                try:
                    search_url = url_pattern.format(query=query)
                    data = await firecrawl_extract(search_url)
                    if data and (data.get("ingredients") or data.get("product_name")):
                        normalized = normalize_firecrawl_result(data)
                        normalized["source"] = source_name.lower().replace(" ", "_")
                        normalized["weight"] = SOURCE_WEIGHTS["specialty_retailer"]
                        results.append(normalized)
                        logger.info(f"Got data from {source_name}")
                        break
                except Exception as e:
                    logger.debug(f"FireCrawl fallback {source_name} failed: {e}")

    # FALLBACK: Use direct scraping if FireCrawl not available or failed
    if not results:
        logger.info("Falling back to direct scraping")

        # Try brand website
        if brand:
            brand_url = get_brand_website(brand)
            if brand_url:
                try:
                    data = await scrape_generic_product_page(
                        f"{brand_url}/search?q={ean or slugify(product_name)}"
                    )
                    if data and data.get("ingredients"):
                        data["source"] = "manufacturer"
                        data["weight"] = SOURCE_WEIGHTS["manufacturer"]
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Brand website scrape failed: {e}")

        # Try suppliers
        for supplier_key, config in SUPPLIER_CONFIGS.items():
            if config.get("requires_login"):
                continue
            try:
                data = await scrape_supplier(config, ean, product_name)
                if data:
                    data["source"] = supplier_key
                    data["weight"] = SOURCE_WEIGHTS["big4_supplier"]
                    results.append(data)
            except Exception as e:
                logger.debug(f"{supplier_key} scrape failed: {e}")

        # Fallback search
        if not results or not any(r.get("ingredients") for r in results):
            query = ean if ean else product_name
            for source_name, url_pattern in FALLBACK_SEARCH_URLS[:2]:
                try:
                    search_url = url_pattern.format(query=query)
                    data = await scrape_generic_product_page(search_url)
                    if data and data.get("ingredients"):
                        data["source"] = source_name.lower().replace(" ", "_")
                        data["weight"] = SOURCE_WEIGHTS["specialty_retailer"]
                        results.append(data)
                        break
                except Exception as e:
                    logger.debug(f"Fallback {source_name} failed: {e}")

    # Merge results, preferring higher-weighted sources
    merged = merge_scraped_data(results)
    merged["_sources"] = [r.get("source", "unknown") for r in results]

    return merged


def normalize_firecrawl_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert FireCrawl extraction result to our standard format

    Args:
        data: FireCrawl extracted data

    Returns:
        Normalized data dict
    """
    normalized = {}

    # Direct mappings
    normalized["ingredients"] = data.get("ingredients", "")
    normalized["description"] = data.get("description", "")
    normalized["allergen_text"] = ", ".join(data.get("allergens", []))

    # Dietary badges from FireCrawl
    dietary_info = data.get("dietary_info", [])
    normalized["dietary_badges"] = dietary_info

    # Nutrition - FireCrawl returns as dict, we need HTML for parser
    nutrition = data.get("nutrition", {})
    if nutrition:
        # Convert dict to simple text for our parser
        nutrition_text = " ".join([
            f"{k}: {v}" for k, v in nutrition.items() if v
        ])
        normalized["nutrition_html"] = f"<div>{nutrition_text}</div>"

    # Other fields
    normalized["weight"] = data.get("weight", "")
    normalized["origin"] = data.get("origin", "")
    normalized["certifications"] = data.get("certifications", [])

    return normalized


async def scrape_supplier(
    config: Dict[str, Any],
    ean: str,
    product_name: str
) -> Optional[Dict[str, Any]]:
    """
    Scrape a single supplier website

    Args:
        config: Supplier configuration dict
        ean: Product EAN
        product_name: Product name

    Returns:
        Scraped data dict or None
    """
    if not HAS_URL_SCRAPER:
        return None

    # Build URL from pattern
    url_pattern = config["product_url_pattern"]
    base_url = config["base_url"]

    # Try EAN first, then slug
    urls_to_try = []
    if ean:
        urls_to_try.append(base_url + url_pattern.format(ean=ean, sku=ean, slug=ean))
    if product_name:
        slug = slugify(product_name)
        urls_to_try.append(base_url + url_pattern.format(ean=slug, sku=slug, slug=slug))

    for url in urls_to_try:
        try:
            # Use existing url_scraper
            result = await asyncio.to_thread(scrape_url, url)
            if result and result.get("success"):
                # Extract specific fields using supplier selectors
                return extract_with_selectors(result.get("html", ""), config["selectors"])
        except Exception as e:
            logger.debug(f"Supplier scrape failed for {url}: {e}")

    return None


async def scrape_generic_product_page(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape a generic product page using the url_scraper

    Args:
        url: Product page URL

    Returns:
        Scraped data dict or None
    """
    if not HAS_URL_SCRAPER:
        return None

    try:
        result = await asyncio.to_thread(scrape_url, url)
        if result and result.get("success"):
            html = result.get("html", "")
            return extract_generic_product_data(html)
    except Exception as e:
        logger.debug(f"Generic scrape failed for {url}: {e}")

    return None


def extract_with_selectors(html: str, selectors: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Extract data from HTML using configured CSS selectors

    Args:
        html: Raw HTML content
        selectors: Dict mapping field names to lists of CSS selectors to try

    Returns:
        Dict with extracted data
    """
    soup = BeautifulSoup(html, 'html.parser')
    data = {}

    for field, selector_list in selectors.items():
        for selector in selector_list:
            try:
                element = soup.select_one(selector)
                if element:
                    if field == "nutrition":
                        # Keep HTML for table parsing
                        data["nutrition_html"] = str(element)
                    elif field == "dietary":
                        # Extract badge texts
                        badges = element.find_all(['span', 'img', 'div'])
                        data["dietary_badges"] = [
                            b.get_text(strip=True) or b.get('alt', '') or b.get('title', '')
                            for b in badges if b.get_text(strip=True) or b.get('alt') or b.get('title')
                        ]
                    else:
                        data[field] = element.get_text(strip=True)
                    break  # Use first matching selector
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")

    return data


def extract_generic_product_data(html: str) -> Dict[str, Any]:
    """
    Extract product data using generic patterns (no supplier-specific selectors)

    Args:
        html: Raw HTML content

    Returns:
        Dict with extracted data
    """
    soup = BeautifulSoup(html, 'html.parser')
    data = {}

    # Generic ingredient selectors
    ingredient_selectors = [
        '.ingredients', '#ingredients', '[class*="ingredient"]',
        '.product-ingredients', '#product-ingredients',
        '[data-ingredients]', '.ingredients-list'
    ]
    for selector in ingredient_selectors:
        element = soup.select_one(selector)
        if element:
            data["ingredients"] = element.get_text(strip=True)
            break

    # Generic nutrition selectors
    nutrition_selectors = [
        '.nutrition', '#nutrition', '.nutritional-info',
        '.nutrition-table', '#nutrition-facts', '[class*="nutri"]',
        'table[class*="nutri"]'
    ]
    for selector in nutrition_selectors:
        element = soup.select_one(selector)
        if element:
            data["nutrition_html"] = str(element)
            break

    # Generic description
    desc_selectors = [
        '.product-description', '#product-description',
        '.description', '[itemprop="description"]',
        '.product-body', '.product-info'
    ]
    for selector in desc_selectors:
        element = soup.select_one(selector)
        if element:
            data["description"] = element.get_text(strip=True)
            break

    return data


def merge_scraped_data(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge data from multiple sources, preferring higher-weighted sources

    Args:
        results: List of scraped data dicts with 'weight' field

    Returns:
        Merged data dict
    """
    if not results:
        return {}

    # Sort by weight descending
    sorted_results = sorted(results, key=lambda x: x.get("weight", 0), reverse=True)

    merged = {}
    fields = ["ingredients", "nutrition_html", "description", "dietary_badges", "allergen_text"]

    for field in fields:
        for result in sorted_results:
            value = result.get(field)
            if value:
                merged[field] = value
                merged[f"{field}_source"] = result.get("source", "unknown")
                break

    return merged
