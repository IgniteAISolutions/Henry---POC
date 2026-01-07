"""
Supplier Configuration for EarthFare Product Scraping
Configure CSS selectors and URL patterns for each supplier

HOW TO FIND SELECTORS:
1. Open supplier website, find a product page
2. Press F12 (or Ctrl+Shift+I) to open dev tools
3. Press Ctrl+Shift+C to enable element picker
4. Click on the element you want (ingredients, nutrition, etc.)
5. Right-click the highlighted HTML → Copy → Copy selector
6. Test in Console: document.querySelector('YOUR_SELECTOR')
"""
from typing import Dict, List, Any

# Main supplier configurations
SUPPLIER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "clf": {
        "name": "CLF Distribution",
        "base_url": "https://www.clf.co.uk",
        "requires_login": True,  # Trade account needed
        "product_url_pattern": "/product/{sku}",
        "search_url": "/search?q={query}",
        "selectors": {
            # TODO: Update these after inspecting actual CLF product pages
            "ingredients": [
                ".product-ingredients",
                ".ingredients-list",
                "[data-ingredients]",
                "#ingredients"
            ],
            "nutrition": [
                ".nutrition-table",
                ".nutritional-info table",
                "#nutrition-facts",
                ".nutrition-panel"
            ],
            "description": [
                ".product-description",
                ".product-info",
                "#product-description",
                "[itemprop='description']"
            ],
            "dietary": [
                ".dietary-info",
                ".product-tags",
                ".badges",
                ".dietary-badges",
                ".product-icons"
            ],
            "allergens": [
                ".allergen-info",
                ".allergy-advice",
                ".contains-allergens"
            ]
        },
        "priority": 1
    },
    "essential": {
        "name": "Essential Trading",
        "base_url": "https://www.essential-trading.coop",
        "requires_login": True,
        "product_url_pattern": "/products/{slug}",
        "search_url": "/search?q={query}",
        "selectors": {
            "ingredients": [
                ".ingredients",
                ".product-ingredients",
                "#ingredients-list"
            ],
            "nutrition": [
                ".nutrition-table",
                ".nutritional-information",
                "#nutrition"
            ],
            "description": [
                ".description",
                ".product-description",
                "#description"
            ],
            "dietary": [
                ".dietary-attributes",
                ".product-badges",
                ".tags"
            ],
            "allergens": [
                ".allergen-info",
                ".allergy-info"
            ]
        },
        "priority": 1
    },
    "suma": {
        "name": "Suma Wholefoods",
        "base_url": "https://www.suma.coop",
        "requires_login": True,
        "product_url_pattern": "/product/{ean}",
        "search_url": "/search?entry={query}",
        "selectors": {
            "ingredients": [
                ".product-ingredients",
                ".ingredients",
                "#product-ingredients"
            ],
            "nutrition": [
                ".nutritional-values",
                ".nutrition-table",
                "#nutritional-info"
            ],
            "description": [
                ".product-description",
                ".description",
                "#product-desc"
            ],
            "dietary": [
                ".product-badges",
                ".dietary-icons",
                ".certifications"
            ],
            "allergens": [
                ".allergen-warning",
                ".allergy-info"
            ]
        },
        "priority": 1
    },
    "infinity": {
        "name": "Infinity Foods",
        "base_url": "https://www.infinityfoods.co.uk",
        "requires_login": False,
        "product_url_pattern": "/products/{slug}",
        "search_url": "/search?q={query}",
        "selectors": {
            "ingredients": [
                ".ingredients-list",
                ".product-ingredients",
                "#ingredients"
            ],
            "nutrition": [
                ".nutrition-info",
                ".nutritional-table",
                "#nutrition-facts"
            ],
            "description": [
                ".product-body",
                ".product-description",
                "#description"
            ],
            "dietary": [
                ".product-icons",
                ".dietary-badges",
                ".certifications"
            ],
            "allergens": [
                ".allergen-info",
                ".allergy-advice"
            ]
        },
        "priority": 1
    }
}

# Fallback search engines when supplier scraping fails
FALLBACK_SEARCH_URLS = [
    # Specialty retailers (medium trust)
    ("Holland & Barrett", "https://www.hollandandbarrett.com/search/?query={query}"),
    ("Planet Organic", "https://www.planetorganic.com/search?q={query}"),
    ("Abel & Cole", "https://www.abelandcole.co.uk/search?q={query}"),

    # Supermarkets (lower trust, but good for basic data)
    ("Ocado", "https://www.ocado.com/search?entry={query}"),
    ("Waitrose", "https://www.waitrose.com/ecom/shop/search?searchTerm={query}"),
]

# Source quality weighting for data merging
SOURCE_WEIGHTS = {
    "manufacturer": 1.0,      # Brand's own website - most trusted
    "big4_supplier": 0.9,     # CLF, Essential, Suma, Infinity
    "specialty_retailer": 0.7, # H&B, Planet Organic
    "supermarket": 0.5,       # Ocado, Waitrose
    "marketplace": 0.1        # Amazon, eBay - mostly ignore
}

# Known brand website patterns (for manufacturer lookups)
BRAND_WEBSITES = {
    "eat real": "https://www.eatreal.co.uk",
    "nkd living": "https://www.nkdliving.com",
    "pulsin": "https://pulsin.co.uk",
    "nakd": "https://eatnakd.com",
    "tribe": "https://wearetribe.co",
    "pip & nut": "https://www.pipandnut.com",
    "meridian": "https://meridianfoods.co.uk",
    "clearspring": "https://www.clearspring.co.uk",
    "biona": "https://www.biona.co.uk",
    "suma": "https://www.suma.coop",
}

# Common product page URL patterns to try
URL_PATTERNS_TO_TRY = [
    "/product/{ean}",
    "/products/{slug}",
    "/p/{sku}",
    "/{slug}",
    "/shop/{slug}",
    "/item/{ean}",
]


def get_supplier_config(supplier_key: str) -> Dict[str, Any]:
    """Get configuration for a specific supplier"""
    return SUPPLIER_CONFIGS.get(supplier_key.lower(), {})


def get_all_supplier_configs() -> Dict[str, Dict[str, Any]]:
    """Get all supplier configurations"""
    return SUPPLIER_CONFIGS


def get_brand_website(brand_name: str) -> str:
    """Look up brand website URL"""
    brand_lower = brand_name.lower().strip()
    return BRAND_WEBSITES.get(brand_lower, "")


def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    import re
    if not text:
        return ""
    slug = text.lower()
    slug = slug.replace("'", "")
    slug = slug.replace("&", "and")
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')
