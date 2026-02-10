"""
Product Enricher for EarthFare
Enriches product data by scraping supplier websites for ingredients,
nutrition, and dietary information.

Integrates:
- OpenFoodFacts API for nutrition (primary for barcode lookup)
- Brand website scraping (Clearspring, etc.)
- FireCrawl API for intelligent scraping
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

# Import OpenFoodFacts service for nutrition lookup
try:
    from .openfoodfacts_service import (
        fetch_nutrition_by_barcode,
        format_off_nutrition_for_shopify
    )
    HAS_OPENFOODFACTS = True
except ImportError:
    HAS_OPENFOODFACTS = False
    logger = logging.getLogger(__name__)
    logger.warning("OpenFoodFacts service not available")

# Import brand scraper for direct website scraping
try:
    from .brand_scraper import scrape_brand_website
    HAS_BRAND_SCRAPER = True
except ImportError:
    HAS_BRAND_SCRAPER = False

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
    from .url_scraper import scrape as scrape_url
    HAS_URL_SCRAPER = True
except ImportError as e:
    HAS_URL_SCRAPER = False
    logger.warning(f"url_scraper not available - limited scraping capability: {e}")


async def enrich_product(product: Dict[str, Any], scrape: bool = True) -> Dict[str, Any]:
    """
    Enrich a single product with nutrition and dietary data

    Data sources (in priority order):
    1. CSV data (already in product dict)
    2. OpenFoodFacts API (barcode lookup)
    3. Supplier website scraping (fallback)

    Args:
        product: Product dict with at least name, and optionally ean/barcode/brand
        scrape: Whether to scrape supplier websites (default True)

    Returns:
        Enriched product dict with ingredients, nutrition, dietary info
    """
    ean = product.get("ean") or product.get("barcode") or product.get("Variant Barcode", "")
    name = product.get("name") or product.get("Title") or product.get("product_name", "")
    brand = product.get("brand") or product.get("Vendor", "")

    logger.info(f"=" * 60)
    logger.info(f"🔄 [ENRICH] Starting enrichment for: {name}")
    logger.info(f"🔄 [ENRICH] Barcode/EAN: '{ean}' (type: {type(ean).__name__})")
    logger.info(f"🔄 [ENRICH] Brand: '{brand}'")
    logger.info(f"🔄 [ENRICH] HAS_OPENFOODFACTS: {HAS_OPENFOODFACTS}")

    # Track nutrition source for transparency
    nutrition_source = product.get("nutrition_source", "")
    nutrition = product.get("nutrition", {})

    # Priority 1: Use nutrition from CSV if already present
    if nutrition and nutrition_source == "csv":
        logger.info(f"Using nutrition data from CSV for {name}")

    # Priority 2: Try OpenFoodFacts if we have a barcode and no nutrition yet
    elif not nutrition and ean and HAS_OPENFOODFACTS:
        logger.info(f"🌐 [ENRICH] OpenFoodFacts lookup - barcode: '{ean}'")
        try:
            off_data = await fetch_nutrition_by_barcode(ean)
            logger.info(f"🌐 [ENRICH] OpenFoodFacts returned: {type(off_data).__name__}")
            if off_data:
                logger.info(f"🌐 [ENRICH] OFF data keys: {list(off_data.keys())}")
                # Get nutrition data (always available if product found)
                nutrition = {k: v for k, v in off_data.items()
                            if k not in ['source', 'product_name', 'brands', 'barcode',
                                        'ingredients_from_off', 'allergens_from_off']}
                nutrition_source = "openfoodfacts"
                logger.info(f"✅ [ENRICH] Got nutrition from OpenFoodFacts: {list(nutrition.keys())}")

                # Also get ingredients and allergens from OFF if available
                if off_data.get("ingredients_from_off") and not product.get("ingredients"):
                    product["ingredients"] = off_data["ingredients_from_off"]
                    product["ingredients_source"] = "openfoodfacts"
                    logger.info(f"✅ [ENRICH] Got ingredients from OpenFoodFacts (length: {len(product['ingredients'])})")

                if off_data.get("allergens_from_off") and not product.get("allergens"):
                    product["allergens"] = off_data["allergens_from_off"]
                    logger.info(f"✅ [ENRICH] Got allergens from OpenFoodFacts: {product['allergens']}")
            else:
                logger.info(f"⚠️ [ENRICH] OpenFoodFacts returned None for barcode '{ean}'")
        except Exception as e:
            logger.warning(f"❌ [ENRICH] OpenFoodFacts lookup failed for '{ean}': {e}")
            import traceback
            logger.warning(f"❌ [ENRICH] Traceback: {traceback.format_exc()}")

    # Priority 2b: Try brand website scraping if we have brand and still missing data
    if HAS_BRAND_SCRAPER and brand and (not nutrition or not product.get("ingredients")):
        logger.info(f"🌐 Trying brand website scraping for {brand}: {name}")
        try:
            brand_data = await scrape_brand_website(brand, name, ean)
            if brand_data:
                # Get nutrition if we don't have it
                if not nutrition and brand_data.get("nutrition"):
                    nutrition = brand_data["nutrition"]
                    nutrition_source = "brand_website"
                    logger.info(f"✅ Got nutrition from {brand} website for {name}")

                # Get ingredients if we don't have them
                if not product.get("ingredients") and brand_data.get("ingredients"):
                    product["ingredients"] = brand_data["ingredients"]
                    product["ingredients_source"] = "brand_website"
                    logger.info(f"✅ Got ingredients from {brand} website for {name}")

                # Get allergens
                if not product.get("allergens") and brand_data.get("allergens"):
                    product["allergens"] = brand_data["allergens"]

                # Store source URL for verification
                if brand_data.get("source_url"):
                    product["data_source_url"] = brand_data["source_url"]
        except Exception as e:
            logger.warning(f"⚠️ Brand website scraping failed for {brand}: {e}")

    # Priority 3: Scrape from supplier websites (fallback)
    scraped_data = {}
    if scrape:
        scraped_data = await scrape_product_data(ean, name, brand)

        # Parse nutrition from scraped HTML if we still don't have it
        if not nutrition and scraped_data.get("nutrition_html"):
            nutrition = parse_nutrition_from_html(scraped_data["nutrition_html"])
            nutrition_source = "scraped"
            logger.info(f"Got nutrition from web scraping for {name}")

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

    # Format nutrition for Shopify
    if nutrition_source == "openfoodfacts":
        nutrition_shopify = format_off_nutrition_for_shopify(nutrition) if HAS_OPENFOODFACTS else []
    else:
        nutrition_shopify = format_nutrition_for_shopify(nutrition)

    # Build data sources summary for UI display
    data_sources = []
    if nutrition_source:
        data_sources.append(f"Nutrition: {nutrition_source}")
    if product.get("ingredients_source"):
        data_sources.append(f"Ingredients: {product.get('ingredients_source')}")
    if scraped_data.get("_sources"):
        data_sources.extend([f"Scraped: {s}" for s in scraped_data.get("_sources", [])])

    # Merge with original product
    enriched = {
        **product,
        "ingredients": ingredients_text,
        "ingredients_list": ingredients_list,
        "nutrition": nutrition,
        "nutrition_shopify": nutrition_shopify,
        "nutrition_source": nutrition_source,
        "ingredients_source": product.get("ingredients_source", ""),
        "dietary": dietary,
        "dietary_preferences": dietary,  # Alias for Shopify export
        "allergens": allergens,
        "may_contain": allergen_statement.get("may_contain", []),
        "description_scraped": scraped_data.get("description", ""),
        "data_sources": data_sources,
        "data_source_url": product.get("data_source_url", ""),
        "_scrape_sources": scraped_data.get("_sources", [])
    }

    logger.info(f"=" * 60)
    logger.info(f"✅ [ENRICH] COMPLETED: {name}")
    logger.info(f"   - Nutrition source: {nutrition_source or 'none'}")
    logger.info(f"   - Ingredients source: {product.get('ingredients_source') or 'none'}")
    logger.info(f"   - Ingredients present: {bool(enriched.get('ingredients'))}")
    logger.info(f"   - Nutrition keys: {list(enriched.get('nutrition', {}).keys())}")
    logger.info(f"   - Dietary flags: {dietary}")
    logger.info(f"   - Allergens: {allergens}")
    logger.info(f"=" * 60)

    return enriched


async def enrich_products(products: List[Dict[str, Any]], scrape: bool = True) -> List[Dict[str, Any]]:
    """
    Enrich multiple products with nutrition and dietary data

    Args:
        products: List of product dicts
        scrape: Whether to scrape supplier websites (default True)

    Returns:
        List of enriched product dicts
    """
    enriched = []
    for i, product in enumerate(products):
        logger.info(f"Processing product {i+1}/{len(products)}")
        try:
            enriched_product = await enrich_product(product, scrape=scrape)
            enriched.append(enriched_product)
        except Exception as e:
            logger.error(f"Failed to enrich product {product.get('name', 'unknown')}: {e}")
            product["_enrichment_error"] = str(e)
            enriched.append(product)

        # Small delay between requests to be respectful (rate limiting)
        await asyncio.sleep(0.6)

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
