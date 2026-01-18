"""
URL Scraper Service - Hybrid cloudscraper + Playwright
Falls back to Playwright for SSL errors and Cloudflare blocks
"""
import logging
import re
import asyncio
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Try cloudscraper first (faster)
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

# Playwright for difficult sites
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from bs4 import BeautifulSoup


async def scrape(url: str, category: str) -> List[Dict[str, Any]]:
    """Scrape product data - tries cloudscraper first, then Playwright"""
    logger.info(f"Scraping URL: {url}")
    
    html = None
    method_used = None
    
    # Try cloudscraper first (faster, handles most Cloudflare)
    if HAS_CLOUDSCRAPER:
        try:
            html = await asyncio.to_thread(scrape_with_cloudscraper, url)
            method_used = "cloudscraper"
            logger.info("Successfully scraped with cloudscraper")
        except Exception as e:
            logger.warning(f"Cloudscraper failed: {e}")
    
    # Fall back to Playwright (handles SSL issues, JS rendering)
    if not html and HAS_PLAYWRIGHT:
        try:
            html = await scrape_with_playwright(url)
            method_used = "playwright"
            logger.info("Successfully scraped with Playwright")
        except Exception as e:
            logger.warning(f"Playwright failed: {e}")
    
    if not html:
        raise ValueError("This website could not be scraped. Please try a different URL or use CSV upload instead.")
    
    # Parse and extract
    soup = BeautifulSoup(html, 'html.parser')
    full_text = soup.get_text(separator=' ', strip=True)
    
    product = {
        "name": extract_product_name(soup, url),
        "brand": extract_brand(soup, full_text),
        "sku": extract_sku(soup, full_text),
        "ean": extract_ean(soup, full_text),
        "barcode": extract_barcode(soup, full_text),
        "mpn": extract_mpn(soup, full_text),
        "category": category,
        "descriptions": {
            "shortDescription": extract_short_description(soup),
            "metaDescription": extract_meta_description(soup),
            "longDescription": extract_long_description(soup)
        },
        "features": extract_features(soup),
        "specifications": extract_specifications(soup, full_text),
        "colours": extract_colours(soup, full_text),
        "sizes": extract_sizes(soup, full_text),
        "warranty": extract_warranty(soup, full_text),
        "pricing": extract_pricing(soup, full_text),
        "images": extract_images(soup),
        # Food/grocery specific fields
        "ingredients": extract_ingredients(soup, full_text),
        "nutrition": extract_nutrition(soup, full_text),
        "allergens": extract_allergens(soup, full_text),
        "dietary_info": extract_dietary_info(soup, full_text),
        "rawExtractedContent": full_text[:5000],
        "_source_url": url,
        "_scrape_method": method_used
    }
    
    return [product]


def scrape_with_cloudscraper(url: str) -> str:
    """Synchronous scrape using cloudscraper"""
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
    response = scraper.get(url, timeout=30)
    response.raise_for_status()
    return response.text


async def scrape_with_playwright(url: str) -> str:
    """Async scrape using Playwright (real browser)"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(2000)
            html = await page.content()
        finally:
            await browser.close()
        
        return html


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_product_name(soup: BeautifulSoup, url: str) -> str:
    selectors = [
        'h1.product-title', 'h1.product_title', 'h1.product-name',
        'h1[itemprop="name"]', '.product-title h1', '.product_title', 'h1'
    ]
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            name = elem.get_text(strip=True)
            if name and len(name) > 2:
                return name
    og = soup.find('meta', property='og:title')
    if og and og.get('content'):
        return og['content'].strip()
    return url.split('/')[-1].replace('-', ' ').replace('_', ' ').title()


def extract_brand(soup: BeautifulSoup, full_text: str) -> str:
    brand_elem = soup.find(attrs={'itemprop': 'brand'})
    if brand_elem:
        name_elem = brand_elem.find(attrs={'itemprop': 'name'})
        if name_elem:
            return name_elem.get_text(strip=True)
        return brand_elem.get_text(strip=True)[:50]
    
    for prop in ['og:brand', 'product:brand']:
        meta = soup.find('meta', property=prop)
        if meta and meta.get('content'):
            return meta['content'].strip()
    
    selectors = ['.product-brand', '.brand', '.manufacturer']
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            return elem.get_text(strip=True)[:50]
    
    match = re.search(r'Brand:\s*([A-Za-z0-9\s&]+)', full_text)
    if match:
        return match.group(1).strip()[:50]
    return ""


def extract_sku(soup: BeautifulSoup, full_text: str) -> str:
    meta = soup.find('meta', attrs={'itemprop': 'sku'})
    if meta and meta.get('content'):
        return meta['content'].strip()
    
    elem = soup.find(attrs={'itemprop': 'sku'})
    if elem:
        return elem.get_text(strip=True)
    
    selectors = ['.sku', '.product-sku', '[data-sku]', '.product_meta .sku']
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            match = re.search(r'([A-Z0-9][-A-Z0-9]+)', text)
            if match:
                return match.group(1)
    
    patterns = [
        r'SKU[:\s]+([A-Z0-9][-A-Z0-9]+)',
        r'Product Code[:\s]+([A-Z0-9][-A-Z0-9]+)',
        r'Item Code[:\s]+([A-Z0-9][-A-Z0-9]+)',
        r'Model[:\s]+([A-Z0-9][-A-Z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_ean(soup: BeautifulSoup, full_text: str) -> str:
    for prop in ['gtin13', 'gtin', 'gtin14', 'gtin12']:
        meta = soup.find('meta', attrs={'itemprop': prop})
        if meta and meta.get('content'):
            return meta['content'].strip()
        elem = soup.find(attrs={'itemprop': prop})
        if elem:
            return elem.get_text(strip=True)
    
    patterns = [r'EAN[:\s]+(\d{13})', r'GTIN[:\s]+(\d{13,14})']
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_barcode(soup: BeautifulSoup, full_text: str) -> str:
    ean = extract_ean(soup, full_text)
    if ean:
        return ean
    patterns = [r'UPC[:\s]+(\d{12})', r'Barcode[:\s]+(\d{8,14})']
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_mpn(soup: BeautifulSoup, full_text: str) -> str:
    meta = soup.find('meta', attrs={'itemprop': 'mpn'})
    if meta and meta.get('content'):
        return meta['content'].strip()
    match = re.search(r'MPN[:\s]+([A-Z0-9][-A-Z0-9]+)', full_text, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def extract_short_description(soup: BeautifulSoup) -> str:
    selectors = [
        '.woocommerce-product-details__short-description',
        '.short-description', '.product-intro', '.product-summary',
        '[itemprop="description"]'
    ]
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text:
                return text[:500]
    return ""


def extract_meta_description(soup: BeautifulSoup) -> str:
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta and meta.get('content'):
        return meta['content'][:160]
    og = soup.find('meta', property='og:description')
    if og and og.get('content'):
        return og['content'][:160]
    return extract_short_description(soup)[:160]


def extract_long_description(soup: BeautifulSoup) -> str:
    selectors = [
        '.woocommerce-Tabs-panel--description', '#tab-description',
        '.product-description', '.description-content', '.product-details'
    ]
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text and len(text) > 50:
                return text[:3000]
    return ""


def extract_features(soup: BeautifulSoup) -> List[str]:
    features = []
    selectors = [
        '.features li', '.product-features li', '.feature-list li',
        '.woocommerce-product-details__short-description li',
        'ul.product-bullets li', '.key-features li'
    ]
    for selector in selectors:
        items = soup.select(selector)
        for item in items[:15]:
            text = item.get_text(strip=True)
            if text and len(text) > 5 and text not in features:
                features.append(text)
    return features[:15]


def extract_specifications(soup: BeautifulSoup, full_text: str) -> Dict[str, Any]:
    specs = {}
    table_selectors = [
        '.woocommerce-product-attributes', 'table.shop_attributes',
        '.specifications table', '.specs table', '.product-specs table'
    ]
    for selector in table_selectors:
        tables = soup.select(selector)
        for table in tables:
            rows = table.select('tr')
            for row in rows:
                cells = row.select('td, th')
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        specs[key] = value
    
    spec_patterns = {
        'dimensions': r'Dimensions?[:\s]+([0-9]+\s*[xX×]\s*[0-9]+(?:\s*[xX×]\s*[0-9]+)?)',
        'weight': r'Weight[:\s]+([0-9.]+\s*(?:kg|g|lb|lbs))',
        'power': r'Power[:\s]+([0-9]+\s*[Ww])',
        'capacity': r'Capacity[:\s]+([0-9.]+\s*(?:L|ml|litres?))',
    }
    for spec_key, pattern in spec_patterns.items():
        if spec_key not in specs:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                specs[spec_key] = match.group(1).strip()
    return specs


def extract_colours(soup: BeautifulSoup, full_text: str) -> List[str]:
    colours = []
    colour_words = [
        'black', 'white', 'silver', 'grey', 'gray', 'red', 'blue', 'green',
        'gold', 'rose gold', 'bronze', 'copper', 'cream', 'stainless steel'
    ]
    text_lower = full_text.lower()
    for colour in colour_words:
        if colour in text_lower:
            colours.append(colour.title())
    return list(set(colours))[:10]


def extract_sizes(soup: BeautifulSoup, full_text: str) -> List[str]:
    sizes = []
    size_selects = soup.select('select[name*="size"], .size-selector select')
    for select in size_selects:
        for option in select.find_all('option'):
            text = option.get_text(strip=True)
            if text and text.lower() not in ['choose', 'select', '']:
                sizes.append(text)
    return list(set(sizes))[:10]


def extract_warranty(soup: BeautifulSoup, full_text: str) -> str:
    patterns = [
        r'(\d+\s*years?\s*(?:warranty|guarantee))',
        r'(warranty[:\s]+\d+\s*years?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_pricing(soup: BeautifulSoup, full_text: str) -> Dict[str, Any]:
    pricing = {}
    price_elem = soup.find(attrs={'itemprop': 'price'})
    if price_elem:
        pricing['price'] = price_elem.get('content') or price_elem.get_text(strip=True)
    
    price_selectors = ['.price', '.product-price', '[data-price]', '.current-price']
    for selector in price_selectors:
        elem = soup.select_one(selector)
        if elem and 'price' not in pricing:
            text = elem.get_text(strip=True)
            match = re.search(r'[£$€][\d,]+\.?\d*', text)
            if match:
                pricing['price'] = match.group(0)
    return pricing


def extract_images(soup: BeautifulSoup) -> List[str]:
    images = []
    gallery_selectors = ['.product-gallery img', '.woocommerce-product-gallery img', '.product-images img']
    for selector in gallery_selectors:
        for img in soup.select(selector)[:10]:
            src = img.get('src') or img.get('data-src')
            if src and src not in images and not src.endswith('.svg'):
                images.append(src)
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        images.insert(0, og_img['content'])
    return images[:10]


# =============================================================================
# FOOD/GROCERY SPECIFIC EXTRACTION
# =============================================================================

def extract_ingredients(soup: BeautifulSoup, full_text: str) -> str:
    """Extract ingredients list from product page"""
    # Try common selectors first
    selectors = [
        '.ingredients', '.product-ingredients', '#ingredients',
        '[data-ingredients]', '.ingredients-list', '.ingredient-list',
        'div[class*="ingredient"]', 'p[class*="ingredient"]',
        # Suma specific
        'h3:contains("Ingredients") + p', 'h2:contains("Ingredients") + p',
    ]
    for selector in selectors:
        try:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 3:
                    return text
        except Exception:
            continue

    # Look for heading followed by content
    for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'b']):
        heading_text = heading.get_text(strip=True).lower()
        if 'ingredient' in heading_text:
            # Get next sibling or parent's next content
            next_elem = heading.find_next_sibling()
            if next_elem:
                text = next_elem.get_text(strip=True)
                if text and len(text) > 3:
                    return text
            # Check parent container
            parent = heading.parent
            if parent:
                text = parent.get_text(strip=True)
                # Remove the heading text
                text = text.replace(heading.get_text(strip=True), '').strip()
                if text and len(text) > 3:
                    return text

    # Regex fallback - look for "Ingredients:" pattern
    patterns = [
        r'Ingredients?[:\s]+([A-Za-z][^\.]{10,500})',
        r'Contains?[:\s]+([A-Za-z][^\.]{5,200})',
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_nutrition(soup: BeautifulSoup, full_text: str) -> Dict[str, Any]:
    """Extract nutritional information table"""
    nutrition = {}

    # Common nutrition table selectors
    table_selectors = [
        '.nutritional-info', '.nutrition-table', '#nutrition',
        '.nutritional-values', 'table[class*="nutri"]',
        '.product-nutrition', '.nutrition-facts',
        # Suma specific
        'table', '.nutritional-information',
    ]

    for selector in table_selectors:
        try:
            tables = soup.select(selector)
            for table in tables:
                rows = table.select('tr')
                for row in rows:
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)

                        # Map common nutrition fields
                        if 'energy' in key and 'kcal' in key.lower():
                            nutrition['energy_kcal'] = value
                        elif 'energy' in key and 'kj' in key.lower():
                            nutrition['energy_kj'] = value
                        elif 'energy' in key:
                            nutrition['energy_kcal'] = value
                        elif 'fat' in key and 'saturate' not in key:
                            nutrition['fat'] = value
                        elif 'saturate' in key:
                            nutrition['saturates'] = value
                        elif 'carbohydrate' in key and 'sugar' not in key:
                            nutrition['carbohydrates'] = value
                        elif 'sugar' in key:
                            nutrition['sugars'] = value
                        elif 'fibre' in key or 'fiber' in key:
                            nutrition['fibre'] = value
                        elif 'protein' in key:
                            nutrition['protein'] = value
                        elif 'salt' in key:
                            nutrition['salt'] = value

                if nutrition:
                    return nutrition
        except Exception:
            continue

    # Regex fallback for text-based nutrition info
    nutrition_patterns = {
        'energy_kcal': r'Energy[:\s]+(\d+\.?\d*)\s*(?:kcal|Kcal)',
        'fat': r'Fat[:\s]+(\d+\.?\d*)\s*g',
        'saturates': r'Saturates?[:\s]+(\d+\.?\d*)\s*g',
        'carbohydrates': r'Carbohydrates?[:\s]+(\d+\.?\d*)\s*g',
        'sugars': r'Sugars?[:\s]+(\d+\.?\d*)\s*g',
        'fibre': r'Fibre[:\s]+(\d+\.?\d*)\s*g',
        'protein': r'Protein[:\s]+(\d+\.?\d*)\s*g',
        'salt': r'Salt[:\s]+(\d+\.?\d*)\s*g',
    }

    for key, pattern in nutrition_patterns.items():
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            nutrition[key] = match.group(1)

    return nutrition


def extract_allergens(soup: BeautifulSoup, full_text: str) -> Dict[str, Any]:
    """Extract allergen and cross-contamination information"""
    allergens = {
        'contains': [],
        'may_contain': [],
        'free_from': []
    }

    # Common allergen selectors
    selectors = [
        '.allergen-info', '.allergens', '.allergy-info',
        '.allergy-warning', '[class*="allergen"]',
        '.cross-contamination', '.may-contain',
    ]

    allergen_keywords = [
        'wheat', 'gluten', 'milk', 'dairy', 'eggs', 'egg', 'nuts', 'peanuts',
        'soya', 'soy', 'sesame', 'fish', 'shellfish', 'crustaceans',
        'celery', 'mustard', 'lupin', 'molluscs', 'sulphur dioxide', 'sulphites'
    ]

    for selector in selectors:
        try:
            elems = soup.select(selector)
            for elem in elems:
                text = elem.get_text(strip=True).lower()
                for allergen in allergen_keywords:
                    if allergen in text:
                        if 'may contain' in text or 'cross contamination' in text or 'may have come in contact' in text:
                            if allergen.title() not in allergens['may_contain']:
                                allergens['may_contain'].append(allergen.title())
                        elif 'free from' in text or 'does not contain' in text:
                            if allergen.title() not in allergens['free_from']:
                                allergens['free_from'].append(allergen.title())
                        else:
                            if allergen.title() not in allergens['contains']:
                                allergens['contains'].append(allergen.title())
        except Exception:
            continue

    # Regex patterns for allergen statements
    may_contain_pattern = r'(?:may contain|cross.?contamination|may have come in contact)[:\s]+([^\.]+)'
    contains_pattern = r'(?:contains|allergens?)[:\s]+([^\.]+)'

    may_match = re.search(may_contain_pattern, full_text, re.IGNORECASE)
    if may_match:
        text = may_match.group(1).lower()
        for allergen in allergen_keywords:
            if allergen in text and allergen.title() not in allergens['may_contain']:
                allergens['may_contain'].append(allergen.title())

    contains_match = re.search(contains_pattern, full_text, re.IGNORECASE)
    if contains_match:
        text = contains_match.group(1).lower()
        for allergen in allergen_keywords:
            if allergen in text and allergen.title() not in allergens['contains']:
                allergens['contains'].append(allergen.title())

    return allergens


def extract_dietary_info(soup: BeautifulSoup, full_text: str) -> List[str]:
    """Extract dietary attributes (vegan, organic, gluten-free, etc.)"""
    dietary_info = []

    dietary_keywords = {
        'vegan': ['vegan', 'plant-based', 'plant based'],
        'vegetarian': ['vegetarian', 'veggie'],
        'organic': ['organic', 'certified organic'],
        'gluten-free': ['gluten free', 'gluten-free', 'no gluten'],
        'dairy-free': ['dairy free', 'dairy-free', 'no dairy'],
        'nut-free': ['nut free', 'nut-free', 'no nuts'],
        'fairtrade': ['fairtrade', 'fair trade'],
        'kosher': ['kosher'],
        'halal': ['halal'],
        'raw': ['raw food', 'raw '],
        'sugar-free': ['sugar free', 'sugar-free', 'no added sugar'],
        'low-salt': ['low salt', 'reduced salt'],
        'high-fibre': ['high fibre', 'high fiber', 'rich in fibre'],
    }

    text_lower = full_text.lower()

    # Check for badge/tag elements
    badge_selectors = [
        '.dietary-badge', '.product-badge', '.tag', '.label',
        '[class*="badge"]', '[class*="tag"]', 'img[alt*="vegan"]',
        'img[alt*="organic"]', '.dietary-groups', '.product-ethics',
    ]

    for selector in badge_selectors:
        try:
            elems = soup.select(selector)
            for elem in elems:
                elem_text = elem.get_text(strip=True).lower()
                alt_text = elem.get('alt', '').lower() if elem.name == 'img' else ''
                combined = elem_text + ' ' + alt_text

                for diet_key, keywords in dietary_keywords.items():
                    for keyword in keywords:
                        if keyword in combined and diet_key not in dietary_info:
                            dietary_info.append(diet_key)
        except Exception:
            continue

    # Check full text for dietary keywords
    for diet_key, keywords in dietary_keywords.items():
        if diet_key not in dietary_info:
            for keyword in keywords:
                if keyword in text_lower:
                    dietary_info.append(diet_key)
                    break

    return dietary_info
