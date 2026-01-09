"""
FireCrawl Integration for EarthFare
Uses FireCrawl API for intelligent web scraping with anti-bot handling
and AI-powered structured data extraction.

FireCrawl handles: proxies, anti-bot, JS rendering, PDF parsing
"""
import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# FireCrawl API configuration
FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Extraction schema for grocery products
PRODUCT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {
            "type": "string",
            "description": "The name of the product"
        },
        "brand": {
            "type": "string",
            "description": "The brand or manufacturer name"
        },
        "ingredients": {
            "type": "string",
            "description": "Full ingredients list as a comma-separated string"
        },
        "nutrition": {
            "type": "object",
            "description": "Nutritional information per 100g",
            "properties": {
                "energy_kcal": {"type": "string"},
                "energy_kj": {"type": "string"},
                "fat": {"type": "string"},
                "saturates": {"type": "string"},
                "carbohydrates": {"type": "string"},
                "sugars": {"type": "string"},
                "fibre": {"type": "string"},
                "protein": {"type": "string"},
                "salt": {"type": "string"}
            }
        },
        "allergens": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of allergens (e.g., ['Milk', 'Nuts', 'Gluten'])"
        },
        "dietary_info": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dietary attributes like Vegan, Gluten Free, Organic"
        },
        "description": {
            "type": "string",
            "description": "Product description or marketing copy"
        },
        "weight": {
            "type": "string",
            "description": "Product weight or volume (e.g., '500g', '1L')"
        },
        "origin": {
            "type": "string",
            "description": "Country of origin if specified"
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Certifications like Organic, Fairtrade, Soil Association"
        }
    },
    "required": ["product_name"]
}


def is_firecrawl_configured() -> bool:
    """Check if FireCrawl API is configured"""
    return bool(FIRECRAWL_API_KEY)


async def scrape_with_firecrawl(
    url: str,
    formats: List[str] = None,
    extract_schema: Dict = None
) -> Optional[Dict[str, Any]]:
    """
    Scrape a URL using FireCrawl API v2

    Args:
        url: URL to scrape
        formats: Output formats (default: ["markdown", "html"])
        extract_schema: JSON schema for structured extraction

    Returns:
        Dict with scraped content or None if failed
    """
    if not is_firecrawl_configured():
        logger.warning("FireCrawl API key not configured")
        return None

    formats = formats or ["markdown", "html"]

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "formats": formats
    }

    # Add extraction if schema provided
    if extract_schema:
        payload["extract"] = {
            "schema": extract_schema
        }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Use v2 endpoint
            response = await client.post(
                f"{FIRECRAWL_API_URL}/v2/scrape",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {})
                else:
                    logger.error(f"FireCrawl scrape failed: {data.get('error')}")
            else:
                logger.error(f"FireCrawl API error: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"FireCrawl request failed: {e}")

    return None


async def extract_product_data(url: str) -> Optional[Dict[str, Any]]:
    """
    Extract structured product data from a URL using FireCrawl's AI extraction

    Args:
        url: Product page URL

    Returns:
        Dict with extracted product data
    """
    result = await scrape_with_firecrawl(
        url,
        formats=["markdown", "html"],
        extract_schema=PRODUCT_EXTRACTION_SCHEMA
    )

    if result and result.get("extract"):
        extracted = result["extract"]

        # Also include raw content for further processing
        extracted["_raw_markdown"] = result.get("markdown", "")
        extracted["_raw_html"] = result.get("html", "")
        extracted["_source_url"] = url

        return extracted

    return result


async def scrape_supplier_product(
    supplier_url: str,
    ean: str = None,
    product_name: str = None
) -> Optional[Dict[str, Any]]:
    """
    Scrape a supplier product page with structured extraction

    Args:
        supplier_url: Base supplier URL or full product URL
        ean: Product EAN/barcode for lookup
        product_name: Product name for search

    Returns:
        Extracted product data or None
    """
    # If it's already a full product URL, scrape directly
    if supplier_url.startswith("http") and ("product" in supplier_url or ean in supplier_url):
        return await extract_product_data(supplier_url)

    # Otherwise, try to construct search URL
    query = ean or product_name
    if not query:
        return None

    # Common search URL patterns
    search_patterns = [
        f"{supplier_url}/search?q={query}",
        f"{supplier_url}/search?query={query}",
        f"{supplier_url}/search?entry={query}",
        f"{supplier_url}/products?search={query}",
    ]

    for search_url in search_patterns:
        try:
            result = await scrape_with_firecrawl(search_url, formats=["links"])
            if result and result.get("links"):
                # Find product link from search results
                product_links = [
                    link for link in result["links"]
                    if "product" in link.lower() or query.lower() in link.lower()
                ]
                if product_links:
                    return await extract_product_data(product_links[0])
        except Exception as e:
            logger.debug(f"Search pattern {search_url} failed: {e}")

    return None


async def discover_page_selectors(url: str) -> Dict[str, str]:
    """
    Use FireCrawl to analyze a page and discover CSS selectors for key elements.
    Useful for configuring new suppliers.

    Args:
        url: Product page URL to analyze

    Returns:
        Dict mapping field names to discovered CSS selectors
    """
    if not is_firecrawl_configured():
        logger.warning("FireCrawl not configured - cannot discover selectors")
        return {}

    # Use AI extraction with a discovery-focused schema
    discovery_schema = {
        "type": "object",
        "properties": {
            "ingredients_selector": {
                "type": "string",
                "description": "CSS selector for the ingredients list element"
            },
            "nutrition_selector": {
                "type": "string",
                "description": "CSS selector for the nutrition table element"
            },
            "description_selector": {
                "type": "string",
                "description": "CSS selector for the product description element"
            },
            "dietary_selector": {
                "type": "string",
                "description": "CSS selector for dietary badges/icons element"
            },
            "allergen_selector": {
                "type": "string",
                "description": "CSS selector for allergen information element"
            },
            "price_selector": {
                "type": "string",
                "description": "CSS selector for the price element"
            }
        }
    }

    # Custom prompt for selector discovery
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": url,
        "formats": ["html"],
        "extract": {
            "prompt": """Analyze this product page HTML and identify the CSS selectors for:
1. Ingredients list (where the product ingredients are listed)
2. Nutrition table (nutritional information per 100g)
3. Product description (marketing copy about the product)
4. Dietary badges (icons/labels showing Vegan, Gluten Free, etc.)
5. Allergen information (contains warnings)

For each, provide the most specific CSS selector that would reliably select that element.
Use class names, IDs, or data attributes where available.""",
            "schema": discovery_schema
        }
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{FIRECRAWL_API_URL}/v2/scrape",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("data", {}).get("extract"):
                    selectors = data["data"]["extract"]
                    return {
                        "ingredients": selectors.get("ingredients_selector", ""),
                        "nutrition": selectors.get("nutrition_selector", ""),
                        "description": selectors.get("description_selector", ""),
                        "dietary": selectors.get("dietary_selector", ""),
                        "allergens": selectors.get("allergen_selector", "")
                    }

    except Exception as e:
        logger.error(f"Selector discovery failed: {e}")

    return {}


async def batch_scrape_products(urls: List[str]) -> List[Dict[str, Any]]:
    """
    Batch scrape multiple product URLs

    Args:
        urls: List of product page URLs

    Returns:
        List of extracted product data dicts
    """
    results = []

    for url in urls:
        try:
            data = await extract_product_data(url)
            if data:
                results.append(data)
            else:
                results.append({"_source_url": url, "_error": "Extraction failed"})

            # Rate limiting - be respectful
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Batch scrape failed for {url}: {e}")
            results.append({"_source_url": url, "_error": str(e)})

    return results


async def map_supplier_website(base_url: str, search_term: str = None) -> List[str]:
    """
    Use FireCrawl's map endpoint to discover product URLs on a supplier site

    Args:
        base_url: Supplier website base URL
        search_term: Optional search term to filter URLs

    Returns:
        List of discovered product URLs
    """
    if not is_firecrawl_configured():
        return []

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "url": base_url,
        "search": search_term,
        "limit": 100
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{FIRECRAWL_API_URL}/v2/map",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # Filter to likely product URLs
                    all_urls = data.get("links", [])
                    product_urls = [
                        url for url in all_urls
                        if any(p in url.lower() for p in ["/product", "/products/", "/item/", "/p/"])
                    ]
                    return product_urls

    except Exception as e:
        logger.error(f"Map request failed: {e}")

    return []


# Convenience function to test FireCrawl on a single URL
async def test_firecrawl(url: str) -> Dict[str, Any]:
    """
    Test FireCrawl on a URL and return all available data

    Args:
        url: URL to test

    Returns:
        Dict with all scraped and extracted data
    """
    result = {
        "url": url,
        "firecrawl_configured": is_firecrawl_configured()
    }

    if not is_firecrawl_configured():
        result["error"] = "FIRECRAWL_API_KEY not set"
        return result

    # Scrape with full extraction
    data = await extract_product_data(url)
    if data:
        result["success"] = True
        result["extracted"] = data
    else:
        result["success"] = False
        result["error"] = "Extraction returned no data"

    return result
