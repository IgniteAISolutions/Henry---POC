"""
Product Search Service
Routes lookups to appropriate APIs:
- EAN/Barcode → EAN-Search.org
- SKU → Google Custom Search / EAN product search fallback
"""
import os
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# API Configuration - keys from environment only
EAN_SEARCH_BASE = "https://api.ean-search.org/api"
EAN_SEARCH_TOKEN = os.getenv("EAN_SEARCH_API_KEY", "")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")


async def lookup_ean(code: str) -> Optional[Dict[str, Any]]:
    """Lookup product by EAN/UPC barcode using EAN-Search.org"""
    if not EAN_SEARCH_TOKEN:
        logger.error("EAN_SEARCH_API_KEY not configured")
        return None
        
    try:
        code = code.strip().replace(" ", "").replace("-", "")
        logger.info(f"Looking up EAN/Barcode: {code}")
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                EAN_SEARCH_BASE,
                params={
                    "token": EAN_SEARCH_TOKEN,
                    "op": "barcode-lookup",
                    "ean": code,
                    "format": "json",
                    "language": 1
                }
            )
            
            logger.info(f"EAN API response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"EAN API response: {data}")
                
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                elif isinstance(data, dict) and data.get("error"):
                    logger.warning(f"EAN API error: {data.get('error')}")
                    
            return None
            
    except Exception as e:
        logger.error(f"EAN lookup failed: {e}")
        return None


async def search_ean_products(name: str) -> List[Dict[str, Any]]:
    """Search products by name using EAN-Search.org"""
    if not EAN_SEARCH_TOKEN:
        logger.error("EAN_SEARCH_API_KEY not configured")
        return []
        
    try:
        logger.info(f"Searching EAN database for: {name}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                EAN_SEARCH_BASE,
                params={
                    "token": EAN_SEARCH_TOKEN,
                    "op": "product-search",
                    "name": name,
                    "format": "json",
                    "language": 1
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    logger.info(f"Found {len(data)} products")
                    return data
                    
            return []
            
    except Exception as e:
        logger.error(f"EAN product search failed: {e}")
        return []


async def search_google(query: str) -> Optional[Dict[str, Any]]:
    """Search Google Custom Search for SKU/product info"""
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        logger.info("Google Custom Search not configured, skipping")
        return None
        
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": query,
                    "num": 5
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                if items:
                    return items[0]
                    
            return None
            
    except Exception as e:
        logger.error(f"Google search failed: {e}")
        return None


async def search(
    query: str,
    category: str = "Electricals",
    search_type: str = "sku"
) -> List[Dict[str, Any]]:
    """
    Main search function - routes to appropriate API based on search_type
    Auto-detects EAN if query is 8, 12, or 13 digits
    Returns LIST of products (for compatibility with brand_voice.generate)
    """
    logger.info(f"Searching for {search_type.upper()}: {query} in category {category}")
    
    # AUTO-DETECT: If query is all digits and 8/12/13 chars, treat as EAN barcode
    clean_query = query.strip().replace(" ", "").replace("-", "")
    if clean_query.isdigit() and len(clean_query) in [8, 12, 13]:
        logger.info(f"Auto-detected EAN/barcode format: {clean_query}")
        search_type = "ean"
    
    product = None
    
    # EAN or BARCODE → Use EAN-Search.org barcode lookup
    if search_type in ["ean", "barcode"]:
        result = await lookup_ean(clean_query)
        
        if result:
            product = {
                "name": result.get("name", f"Product {query}"),
                "brand": "",
                "sku": "",
                "ean": result.get("ean", query),
                "barcode": result.get("ean", query),
                "category": category,
                "source": "ean-search",
                "rawExtractedContent": f"Product: {result.get('name', '')}. Category: {result.get('categoryName', '')}. Origin: {result.get('issuingCountry', 'Unknown')}.",
                "features": [],
                "specifications": {
                    "ean": result.get("ean", ""),
                    "categoryId": result.get("categoryId", ""),
                    "categoryName": result.get("categoryName", ""),
                    "issuingCountry": result.get("issuingCountry", "")
                },
                "descriptions": {
                    "shortDescription": "",
                    "metaDescription": "",
                    "longDescription": ""
                }
            }
            logger.info(f"Found product via EAN lookup: {product['name']}")
    
    # SKU → Try Google first, then EAN product search
    elif search_type == "sku":
        google_result = await search_google(query)
        
        if google_result:
            product = {
                "name": google_result.get("title", f"Product {query}"),
                "brand": "",
                "sku": query,
                "ean": "",
                "barcode": "",
                "category": category,
                "source": "google",
                "rawExtractedContent": google_result.get("snippet", ""),
                "features": [],
                "specifications": {},
                "descriptions": {
                    "shortDescription": "",
                    "metaDescription": "",
                    "longDescription": ""
                }
            }
            logger.info(f"Found product via Google: {product['name']}")
        else:
            # Fall back to EAN product name search
            results = await search_ean_products(query)
            
            if results:
                result = results[0]
                product = {
                    "name": result.get("name", f"Product {query}"),
                    "brand": "",
                    "sku": query,
                    "ean": result.get("ean", ""),
                    "barcode": result.get("ean", ""),
                    "category": category,
                    "source": "ean-search",
                    "rawExtractedContent": f"Product: {result.get('name', '')}",
                    "features": [],
                    "specifications": {
                        "ean": result.get("ean", ""),
                        "categoryName": result.get("categoryName", "")
                    },
                    "descriptions": {
                        "shortDescription": "",
                        "metaDescription": "",
                        "longDescription": ""
                    }
                }
                logger.info(f"Found product via EAN search: {product['name']}")
    
    # If nothing found, return minimal product
    if not product:
        logger.warning(f"No product found for {search_type}: {query}")
        product = {
            "name": f"Unknown Product ({query})",
            "brand": "",
            "sku": query if search_type == "sku" else "",
            "ean": query if search_type in ["ean", "barcode"] else "",
            "barcode": query if search_type == "barcode" else "",
            "category": category,
            "source": "not-found",
            "rawExtractedContent": f"Product lookup failed for {search_type}: {query}. Please provide more product details.",
            "features": [],
            "specifications": {},
            "descriptions": {
                "shortDescription": "",
                "metaDescription": "",
                "longDescription": ""
            }
        }
    
    # Return as LIST (main.py expects list for brand_voice)
    return [product]
