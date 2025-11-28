"""
URL Scraper Service
Scrape product information from website URLs.
"""
import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import re

class URLScraper:
    """Scrape product pages"""

    def __init__(self):
        self.session = None

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session"""
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
        return self.session

    def extract_product_schema(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        Extract product data from JSON-LD schema.
        Many e-commerce sites use structured data.
        """
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                import json
                data = json.loads(script.string)

                if isinstance(data, dict):
                    if data.get('@type') == 'Product':
                        return data
                    # Sometimes nested
                    if 'Product' in str(data):
                        for key, value in data.items():
                            if isinstance(value, dict) and value.get('@type') == 'Product':
                                return value
            return None
        except Exception as e:
            print(f"[Scraper] Error extracting schema: {e}")
            return None

    def extract_product_info(self, html: str, url: str) -> Dict[str, Any]:
        """
        Extract product information from HTML.
        Uses multiple strategies to find product data.
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Try structured data first
        schema_data = self.extract_product_schema(soup)

        if schema_data:
            # We have structured data!
            name = schema_data.get('name', 'Product from URL')
            brand = schema_data.get('brand', {})
            if isinstance(brand, dict):
                brand = brand.get('name', '')

            description = schema_data.get('description', '')

            # Get offers/price
            offers = schema_data.get('offers', {})
            price = None
            if isinstance(offers, dict):
                price = offers.get('price', None)

            sku = schema_data.get('sku', '')
            gtin = schema_data.get('gtin13') or schema_data.get('gtin') or schema_data.get('ean', '')

            return {
                "name": name,
                "brand": brand,
                "sku": sku,
                "barcode": gtin,
                "description": description,
                "price": price,
            }

        # Fallback: scrape manually
        print("[Scraper] No structured data, using manual extraction")

        # Try to find product title
        name = None
        title_selectors = [
            'h1.product-title',
            'h1[itemprop="name"]',
            '.product-name',
            'h1',
        ]
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                name = element.get_text(strip=True)
                break

        # Try to find description
        description = None
        desc_selectors = [
            '.product-description',
            '[itemprop="description"]',
            '.description',
        ]
        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                description = element.get_text(strip=True)
                break

        # Try to find price
        price = None
        price_selectors = [
            '.price',
            '[itemprop="price"]',
            '.product-price',
        ]
        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = element.get_text(strip=True)
                # Extract numeric value
                price_match = re.search(r'[\d,]+\.?\d*', price_text)
                if price_match:
                    price = price_match.group(0).replace(',', '')
                break

        # Try to find SKU
        sku = None
        sku_patterns = [r'SKU[:\s]+([A-Z0-9-]+)', r'Product Code[:\s]+([A-Z0-9-]+)']
        page_text = soup.get_text()
        for pattern in sku_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                sku = match.group(1)
                break

        return {
            "name": name or "Product from URL",
            "brand": "",
            "sku": sku or "",
            "barcode": "",
            "description": description or "",
            "price": price,
        }

    async def scrape_url(self, url: str) -> Dict[str, Any]:
        """
        Scrape a product URL.

        Args:
            url: Product page URL

        Returns:
            Product information
        """
        print(f"[Scraper] Scraping URL: {url}")

        session = await self._get_session()

        try:
            response = await session.get(url)
            response.raise_for_status()
            html = response.text

            # Extract product info
            product_info = self.extract_product_info(html, url)

            # Format as product
            product = {
                "id": f"url-{hash(url)}",
                "name": product_info.get("name", "Product from URL"),
                "brand": product_info.get("brand", ""),
                "sku": product_info.get("sku", ""),
                "barcode": product_info.get("barcode", ""),
                "source": "url-scrape",
                "rawExtractedContent": product_info.get("description", ""),
                "descriptions": {
                    "shortDescription": product_info.get("description", "")[:200],
                    "metaDescription": product_info.get("description", "")[:160],
                    "longDescription": product_info.get("description", ""),
                },
                "price": product_info.get("price"),
                "specifications": {
                    "source_url": url,
                },
            }

            print(f"[Scraper] Extracted: {product['name']}")
            return product

        except Exception as e:
            print(f"[Scraper] Error scraping {url}: {e}")
            raise

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.aclose()
            self.session = None

# Singleton instance
url_scraper = URLScraper()
