"""
EAN Lookup Service
Uses EAN-Search.org API for barcode/product lookups
"""
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

EAN_SEARCH_BASE = "https://api.ean-search.org/api"

async def lookup_ean(ean: str, token: str) -> Optional[Dict[str, Any]]:
    """Lookup product by EAN/UPC barcode"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                EAN_SEARCH_BASE,
                params={
                    "token": token,
                    "op": "barcode-lookup",
                    "ean": ean,
                    "format": "json",
                    "language": 1  # English
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return None
    except Exception as e:
        logger.error(f"EAN lookup failed: {e}")
        return None

async def search_product(name: str, token: str, page: int = 0) -> List[Dict[str, Any]]:
    """Search products by name"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                EAN_SEARCH_BASE,
                params={
                    "token": token,
                    "op": "product-search",
                    "name": name,
                    "format": "json",
                    "language": 1,
                    "page": page
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logger.error(f"Product search failed: {e}")
        return []

async def lookup(
    ean: Optional[str] = None,
    sku: Optional[str] = None,
    barcode: Optional[str] = None,
    text: Optional[str] = None,
    category: str = "Electricals",
    token: str = ""
) -> List[Dict[str, Any]]:
    """
    Main lookup function - tries EAN first, then product search
    """
    if not token:
        raise ValueError("EAN_SEARCH_API_KEY not configured")
    
    products = []
    
    # Try barcode lookup first (fastest, most accurate)
    code = ean or barcode
    if code:
        # Clean the code
        code = code.strip().replace(" ", "").replace("-", "")
        result = await lookup_ean(code, token)
        if result:
            products.append({
                "name": result.get("name", ""),
                "brand": "",
                "sku": sku or "",
                "ean": result.get("ean", code),
                "category": category,
                "descriptions": {
                    "shortDescription": f"{result.get('name', '')} - {result.get('categoryName', '')}",
                    "metaDescription": result.get("name", "")[:160],
                    "longDescription": f"Product: {result.get('name', '')}. Category: {result.get('categoryName', '')}. Origin: {result.get('issuingCountry', 'Unknown')}."
                },
                "features": [],
                "specifications": {
                    "ean": result.get("ean", ""),
                    "categoryId": result.get("categoryId", ""),
                    "categoryName": result.get("categoryName", ""),
                    "issuingCountry": result.get("issuingCountry", "")
                }
            })
            return products
    
    # Try text/product name search
    if text:
        results = await search_product(text, token)
        for result in results[:5]:  # Limit to 5 results
            products.append({
                "name": result.get("name", ""),
                "brand": "",
                "sku": sku or "",
                "ean": result.get("ean", ""),
                "category": category,
                "descriptions": {
                    "shortDescription": f"{result.get('name', '')}",
                    "metaDescription": result.get("name", "")[:160],
                    "longDescription": f"Product: {result.get('name', '')}. Category: {result.get('categoryName', '')}."
                },
                "features": [],
                "specifications": {
                    "ean": result.get("ean", ""),
                    "categoryName": result.get("categoryName", "")
                }
            })
    
    if not products:
        raise ValueError("No products found for the given search criteria")
    
    return products
