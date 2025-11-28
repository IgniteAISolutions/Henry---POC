"""
Product Search Service
Search products by SKU, EAN, Barcode using EAN-Search API.
"""
import httpx
from typing import Dict, Any, Optional, List
from app.config import config

class ProductSearch:
    """Search for products using EAN-Search API"""

    def __init__(self):
        self.api_key = config.EAN_SEARCH_API_KEY
        self.api_url = config.EAN_SEARCH_API_URL
        self.session = None

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session"""
        if self.session is None:
            self.session = httpx.AsyncClient(timeout=30.0)
        return self.session

    async def search_by_ean(self, ean: str) -> Optional[Dict[str, Any]]:
        """
        Search product by EAN code.

        API Documentation: https://www.ean-search.org/premium/

        Args:
            ean: EAN/GTIN code (8, 12, or 13 digits)

        Returns:
            Product information or None
        """
        if not self.api_key:
            raise ValueError("EAN_SEARCH_API_KEY not configured")

        url = f"{self.api_url}"
        params = {
            "token": self.api_key,
            "op": "barcode-lookup",
            "ean": ean,
            "format": "json"
        }

        session = await self._get_session()

        try:
            response = await session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                return data[0]  # Return first result

            return None

        except Exception as e:
            print(f"[EAN-Search] Error searching {ean}: {e}")
            return None

    def format_product_from_ean(self, ean_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        """
        Format EAN-Search API response into our product format.

        EAN-Search returns:
        - name: Product name
        - categoryName: Category
        - issuing_country: Country
        - ean: EAN code
        - etc.
        """
        return {
            "id": f"ean-{ean_data.get('ean', search_term)}",
            "name": ean_data.get("name", "Product from EAN"),
            "brand": ean_data.get("issuing_country", ""),  # API doesn't always have brand
            "sku": search_term,
            "barcode": ean_data.get("ean", search_term),
            "source": "ean-search",
            "specifications": {
                "category": ean_data.get("categoryName", ""),
                "issuing_country": ean_data.get("issuing_country", ""),
            },
            "descriptions": {
                "shortDescription": ean_data.get("name", ""),
                "metaDescription": ean_data.get("name", ""),
                "longDescription": ean_data.get("name", ""),
            },
        }

    async def search_product(
        self,
        sku: Optional[str] = None,
        barcode: Optional[str] = None,
        ean: Optional[str] = None,
        text: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for products using various identifiers.

        Priority order: EAN > Barcode > SKU > Text

        Returns:
            List of matching products
        """
        products = []

        # Try EAN first
        search_code = ean or barcode or sku or text

        if not search_code:
            raise ValueError("At least one search parameter required")

        print(f"[Product Search] Searching for: {search_code}")

        # Try EAN search
        if search_code and search_code.isdigit() and len(search_code) in [8, 12, 13]:
            ean_result = await self.search_by_ean(search_code)
            if ean_result:
                product = self.format_product_from_ean(ean_result, search_code)
                products.append(product)
                print(f"[Product Search] Found via EAN: {product['name']}")

        # If no results, create a basic product shell
        if not products:
            print(f"[Product Search] No results found, creating basic product")
            products.append({
                "id": f"search-{search_code}",
                "name": f"Product {search_code}",
                "brand": "",
                "sku": sku or search_code,
                "barcode": barcode or ean or "",
                "source": "manual-search",
                "descriptions": {
                    "shortDescription": f"Product with code {search_code}",
                    "metaDescription": f"Product {search_code}",
                    "longDescription": f"Product identified by code {search_code}. Additional details needed.",
                },
                "specifications": {
                    "search_term": search_code,
                },
            })

        return products

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.aclose()
            self.session = None

# Singleton instance
product_search = ProductSearch()
