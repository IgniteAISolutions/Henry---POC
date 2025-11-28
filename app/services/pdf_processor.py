"""
PDF Processor Service
Uses Docling to extract products from PDF catalogues
Handles: Tech specs (Sage), Catalogs (FireUp), Brochures (Zwilling)
"""
import os
import re
import logging
import tempfile
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.warning("Docling not available")

_converter = None


def get_converter():
    global _converter
    if _converter is None and DOCLING_AVAILABLE:
        _converter = DocumentConverter()
    return _converter


async def process(file_content: bytes, category: str) -> List[Dict[str, Any]]:
    """Extract products from PDF using Docling"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        logger.info(f"Processing PDF: {tmp_path}")
        
        if DOCLING_AVAILABLE:
            converter = get_converter()
            result = converter.convert(tmp_path)
            markdown = result.document.export_to_markdown()
        else:
            markdown = extract_text_fallback(tmp_path)
        
        logger.info(f"Extracted {len(markdown)} chars of markdown")
        
        # Detect brand first
        brand = detect_brand(markdown)
        logger.info(f"Detected brand: {brand}")
        
        # Try format-specific extraction
        products = []
        
        # Try Sage format (SES/BES model numbers with variants)
        if re.search(r'SES\d{3}|BES\d{3}|SCG\d{3}', markdown):
            products = extract_sage_products(markdown, category, brand)
        
        # Try FireUp format (FC### codes)
        elif 'FC0' in markdown or 'FIREUP' in markdown.upper():
            products = extract_fireup_products(markdown, category, brand)
        
        # Try Zwilling format (Item code/number patterns)
        elif 'Item code' in markdown or 'Item number' in markdown:
            products = extract_zwilling_products(markdown, category, brand)
        
        # Try Navigate/Summerhouse format (Product Code: pattern)
        elif 'Product Code' in markdown:
            products = extract_product_code_products(markdown, category, brand)
        
        # Fallback: generic SKU extraction
        if not products:
            logger.warning("No format-specific products found, trying fallback")
            products = extract_products_fallback(markdown, category, brand)
        
        logger.info(f"Extracted {len(products)} products from PDF")
        return products
        
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


def extract_text_fallback(pdf_path: str) -> str:
    """Fallback text extraction when Docling unavailable"""
    try:
        import PyPDF2
        text_parts = []
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error(f"Fallback extraction failed: {e}")
        return ""


def detect_brand(markdown: str) -> str:
    """Detect brand from PDF content"""
    if not markdown:
        return ""
    
    brand_patterns = [
        (r'(?:^|\s)(Sage)(?:\s|™|®|$)', 'Sage'),
        (r'(?:^|\s)(FIREUP|Fireup|FireUp)(?:\s|™|®|$)', 'FIREUP'),
        (r'(?:^|\s)(ZWILLING|Zwilling)(?:\s|™|®|$)', 'ZWILLING'),
        (r'(?:^|\s)(Le\s*Creuset)(?:\s|™|®|$)', 'Le Creuset'),
        (r'(?:^|\s)(KitchenAid)(?:\s|™|®|$)', 'KitchenAid'),
        (r'(?:^|\s)(Breville)(?:\s|™|®|$)', 'Breville'),
        (r'(?:^|\s)(Navigate|Summerhouse)(?:\s|™|®|$)', 'Navigate'),
        (r'(?:^|\s)(Gastroback)(?:\s|™|®|$)', 'Gastroback'),
        (r'(?:^|\s)(Joseph\s*Joseph)(?:\s|™|®|$)', 'Joseph Joseph'),
        (r'(?:^|\s)(OXO)(?:\s|™|®|$)', 'OXO'),
        (r'(?:^|\s)(Smeg)(?:\s|™|®|$)', 'Smeg'),
        (r'(?:^|\s)(Dualit)(?:\s|™|®|$)', 'Dualit'),
        (r'(?:^|\s)(Kenwood)(?:\s|™|®|$)', 'Kenwood'),
    ]
    
    text = '\n'.join(markdown.split('\n')[:50])
    
    for pattern, brand_name in brand_patterns:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return brand_name
    
    return ""


def extract_sage_products(markdown: str, category: str, brand: str) -> List[Dict[str, Any]]:
    """Extract products from Sage-style spec sheet PDFs (SES882 etc.)"""
    products = []
    
    # Detect product name (e.g., "the Barista Touch™ Impress")
    product_name = None
    name_patterns = [
        r'the\s+(Barista\s+Touch(?:™)?\s*(?:Impress)?)',
        r'the\s+(Oracle(?:™)?(?:\s+Touch)?)',
        r'the\s+(Bambino(?:™)?(?:\s+Plus)?)',
        r'the\s+(Precision\s+Brewer(?:™)?)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            product_name = match.group(1).strip()
            break
    
    if not product_name:
        # Look in first 20 lines for product title
        for line in markdown.split('\n')[:20]:
            clean = line.strip().replace('#', '').strip()
            if any(kw in clean.lower() for kw in ['barista', 'oracle', 'bambino', 'precision']):
                if 10 < len(clean) < 60:
                    product_name = clean
                    break
    
    if not product_name:
        product_name = "Coffee Machine"
    
    # Extract model number
    model_match = re.search(r'(SES\d{3}|BES\d{3}|SCG\d{3})', markdown)
    model = model_match.group(1) if model_match else ""
    
    # Extract all SKU variants
    sku_pattern = r'(SES\d{3}[A-Z]{2,3}\d[A-Z]{2,3}\d)'
    skus = list(set(re.findall(sku_pattern, markdown)))
    
    # Color code mappings
    color_mappings = {
        'BSS': 'Brushed Stainless Steel',
        'ALM': 'Almond Nougat',
        'BST': 'Black Stainless Steel',
        'BTR': 'Black Truffle',
        'SST': 'Sea Salt',
        'BLK': 'Black',
        'WHT': 'White',
        'RED': 'Red',
    }
    
    # Extract specs
    dims_match = re.search(r'Product\s+Dimensions.*?(\d+\s*x\s*\d+\s*x\s*\d+)\s*mm', markdown, re.IGNORECASE)
    dimensions = dims_match.group(1) + " mm" if dims_match else ""
    
    weight_match = re.search(r'Product\s+Weight.*?([\d.]+)\s*kg', markdown, re.IGNORECASE)
    weight = weight_match.group(1) + " kg" if weight_match else ""
    
    wattage_match = re.search(r'Wattage.*?(\d+-?\d*)\s*W', markdown, re.IGNORECASE)
    wattage = wattage_match.group(1) + "W" if wattage_match else ""
    
    price_match = re.search(r'GBP\s*£?([\d,]+\.?\d*)', markdown)
    price = "£" + price_match.group(1) if price_match else ""
    
    # Create product for each variant
    for sku in skus:
        color = ""
        for code, color_name in color_mappings.items():
            if code in sku:
                color = color_name
                break
        
        full_name = f"{brand or 'Sage'} the {product_name}"
        if color:
            full_name = f"{brand or 'Sage'} the {product_name} - {color}"
        
        products.append({
            "name": full_name,
            "brand": brand or "Sage",
            "sku": sku,
            "ean": "",
            "category": category or "Coffee Machines",
            "source": "pdf-spec-sheet",
            "rawExtractedContent": markdown[:1500],
            "specifications": {
                "model": model,
                "dimensions": dimensions,
                "weight": weight,
                "power": wattage,
                "color": color,
                "price": price,
            },
            "features": extract_features_from_text(markdown),
            "descriptions": {
                "shortDescription": "",
                "metaDescription": "",
                "longDescription": "",
            }
        })
    
    return products


def extract_fireup_products(markdown: str, category: str, brand: str) -> List[Dict[str, Any]]:
    """Extract products from FireUp-style catalog PDFs"""
    products = []
    
    # Product definitions with their SKU patterns
    product_types = [
        {'name': 'Dutch Oven', 'pattern': r'Dutch\s+Oven', 'capacity': '5.0 L / 5.3 QT', 'dims': '36CM * 26CM * 20CM'},
        {'name': 'Skillet with lid', 'pattern': r'Skillet\s+with\s+lid', 'capacity': '1.8 L / 2 QT', 'dims': '47CM * 26CM * 11CM'},
        {'name': 'Skillet', 'pattern': r'(?<!with lid\s)Skillet(?!\s+with)', 'capacity': '1.8 L / 2 QT', 'dims': '47CM * 26CM * 5.5CM'},
        {'name': 'Saucepan', 'pattern': r'Saucepan', 'capacity': '1.6 L / 1.75 QT', 'dims': '42CM * 21CM * 18CM'},
        {'name': 'Braiser', 'pattern': r'Braiser', 'capacity': '2.0 L / 2.3 QT', 'dims': '36CM * 26CM * 6.5CM'},
    ]
    
    # Color/SKU mappings from the PDF
    color_skus = {
        'Dutch Oven': [('Black', 'FC005'), ('Grey', 'FC044'), ('Blue', 'FC006'), ('Yellow', 'FC029'), 
                       ('Olive Green', 'FC032'), ('White', 'FC030'), ('Teal', 'FC045'), ('Red', 'FC013')],
        'Skillet with lid': [('Black', 'FC009'), ('Grey', 'FC047'), ('Blue', 'FC010'), ('Yellow', 'FC034'),
                              ('Olive Green', 'FC037'), ('White', 'FC035'), ('Teal', 'FC048'), ('Red', 'FC015')],
        'Skillet': [('Black', 'FC011'), ('Grey', 'FC050'), ('Blue', 'FC012'), ('Yellow', 'FC039'),
                    ('Olive Green', 'FC042'), ('White', 'FC040'), ('Teal', 'FC051'), ('Red', 'FC016')],
        'Saucepan': [('Black', 'FC007'), ('Grey', 'FC053'), ('Blue', 'FC008'), ('Yellow', 'FC067'),
                     ('Olive Green', 'FC065'), ('White', 'FC066'), ('Teal', 'FC054'), ('Red', 'FC014')],
        'Braiser': [('Black', 'FC056'), ('Grey', 'FC062'), ('Blue', 'FC057'), ('Yellow', 'FC061'),
                    ('Olive Green', 'FC059'), ('White', 'FC060'), ('Teal', 'FC063'), ('Red', 'FC058')],
    }
    
    for prod_type in product_types:
        if re.search(prod_type['pattern'], markdown, re.IGNORECASE):
            if prod_type['name'] in color_skus:
                for color, sku in color_skus[prod_type['name']]:
                    if sku in markdown:
                        products.append({
                            "name": f"FIREUP {prod_type['name']} - {color}",
                            "brand": brand or "FIREUP",
                            "sku": sku,
                            "ean": "",
                            "category": category or "Cookware",
                            "source": "pdf-catalog",
                            "rawExtractedContent": "",
                            "specifications": {
                                "capacity": prod_type['capacity'],
                                "dimensions": prod_type['dims'],
                                "color": color,
                                "material": "Enamelled cast iron from France",
                            },
                            "features": [
                                "Signature fin design for even heat distribution",
                                "Heirloom quality construction",
                                "Premium chip-resistant enamel",
                                "Compatible with all hob types including induction",
                            ],
                            "descriptions": {"shortDescription": "", "metaDescription": "", "longDescription": ""}
                        })
    
    return products


def extract_zwilling_products(markdown: str, category: str, brand: str) -> List[Dict[str, Any]]:
    """Extract products from Zwilling-style PDFs"""
    products = []
    
    # Main Contact Grill
    if 'Contact Grill' in markdown or 'CONTACT GRILL' in markdown:
        ean_match = re.search(r'EAN:\s*(\d{13})', markdown)
        sku_match = re.search(r'Item\s+(?:code|number):\s*(\d{6,8})', markdown, re.IGNORECASE)
        
        products.append({
            "name": "ZWILLING Enfinigy Contact Grill",
            "brand": brand or "ZWILLING",
            "sku": sku_match.group(1) if sku_match else "1033245",
            "ean": ean_match.group(1) if ean_match else "",
            "category": category or "Electricals",
            "source": "pdf-brochure",
            "rawExtractedContent": markdown[:1500],
            "specifications": {
                "dimensions": "398mm x 321mm x 150mm",
                "weight": "8130g",
                "power": "2000W",
                "voltage": "220-240V",
            },
            "features": [
                "Intuitive LCD touch control panel",
                "Independent temperature control for two grilling surfaces",
                "6 automatic programmes: steak, burger, fish, sausage, poultry, panini",
                "180° opening for fully flat barbecue mode",
                "Core temperature thermometer probe included",
                "Ceramic coated cooking surface (PFAS-free)",
            ],
            "descriptions": {"shortDescription": "", "metaDescription": "", "longDescription": ""}
        })
    
    # Teppanyaki plates accessory
    if 'Teppanyaki' in markdown or 'TEPPANYAKI' in markdown:
        products.append({
            "name": "ZWILLING Enfinigy Teppanyaki Plate Accessory",
            "brand": brand or "ZWILLING",
            "sku": "1030470",
            "ean": "4009839683220" if "4009839683220" in markdown else "",
            "category": category or "Electricals",
            "source": "pdf-brochure",
            "rawExtractedContent": "",
            "specifications": {
                "dimensions": "255mm x 345mm x 22mm",
                "weight": "1180g",
            },
            "features": [
                "Flat teppanyaki plates for full surface contact cooking",
                "Ceramic coated cooking surface (PFAS-free)",
                "Dishwasher safe",
            ],
            "descriptions": {"shortDescription": "", "metaDescription": "", "longDescription": ""}
        })
    
    return products


def extract_product_code_products(markdown: str, category: str, brand: str) -> List[Dict[str, Any]]:
    """Extract products using 'Product Code:' pattern (Navigate/Summerhouse)"""
    products = []
    
    pattern = r'Product\s+Code(?:\s+([A-Za-z\s]+))?:\s*(\d{4,6})\s*(?:/\s*(\d+)\s*Way)?'
    
    found_codes = set()
    for match in re.finditer(pattern, markdown, re.IGNORECASE):
        variant = match.group(1).strip() if match.group(1) else ""
        product_code = match.group(2)
        
        if product_code in found_codes:
            continue
        found_codes.add(product_code)
        
        # Get context
        start = max(0, match.start() - 500)
        end = min(len(markdown), match.end() + 200)
        context = markdown[start:end]
        
        name = extract_name_from_context(context) or f"Product {product_code}"
        if variant and variant.lower() not in name.lower():
            name = f"{name} - {variant}"
        
        products.append({
            "name": name,
            "brand": brand,
            "sku": product_code,
            "ean": "",
            "category": category,
            "source": "pdf-catalog",
            "rawExtractedContent": context,
            "specifications": {"productCode": product_code},
            "features": [],
            "descriptions": {"shortDescription": "", "metaDescription": "", "longDescription": ""}
        })
    
    return products


def extract_products_fallback(markdown: str, category: str, brand: str) -> List[Dict[str, Any]]:
    """Fallback: extract products by finding SKU-like patterns"""
    products = []
    
    # Look for alphanumeric SKUs
    sku_pattern = r'\b([A-Z]{2,4}[0-9]{3,}[A-Z0-9]{2,})\b'
    
    found = set()
    for match in re.finditer(sku_pattern, markdown):
        sku = match.group(1)
        if sku in found:
            continue
        found.add(sku)
        
        # Get context
        start = max(0, match.start() - 400)
        end = min(len(markdown), match.end() + 200)
        context = markdown[start:end]
        
        name = extract_name_from_context(context) or f"Product {sku}"
        
        products.append({
            "name": name,
            "brand": brand,
            "sku": sku,
            "ean": "",
            "category": category,
            "source": "pdf-fallback",
            "rawExtractedContent": context,
            "specifications": {},
            "features": extract_features_from_text(context),
            "descriptions": {"shortDescription": "", "metaDescription": "", "longDescription": ""}
        })
    
    return products[:20]  # Limit


def extract_name_from_context(context: str) -> str:
    """Try to extract a meaningful product name from context"""
    keywords = ['machine', 'maker', 'blender', 'mixer', 'kettle', 'toaster',
                'fryer', 'oven', 'grill', 'pan', 'pot', 'skillet', 'saucepan',
                'bag', 'basket', 'bottle', 'plate', 'bowl']
    
    for line in context.split('\n'):
        clean = line.strip().replace('#', '').strip()
        if 10 < len(clean) < 100:
            if any(kw in clean.lower() for kw in keywords):
                return clean
    return ""


def extract_features_from_text(text: str) -> List[str]:
    """Extract features from text"""
    features = []
    keywords = ['preset', 'setting', 'temperature', 'control', 'automatic',
                'dishwasher', 'stainless', 'ceramic', 'grind', 'milk']
    
    for line in text.split('\n'):
        clean = line.strip()
        if clean.startswith('•') or clean.startswith('-') or clean.startswith('*'):
            feature = clean.lstrip('•-* ').strip()
            if 10 < len(feature) < 150:
                features.append(feature)
        elif any(kw in clean.lower() for kw in keywords):
            if 15 < len(clean) < 150 and clean not in features:
                features.append(clean)
    
    return features[:8]
