# app/main.py - Complete Universal API with React Frontend
import os
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging - filter out noisy health probe warnings
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Filter out "Invalid HTTP request received" warnings from uvicorn
class InvalidHTTPFilter(logging.Filter):
    def filter(self, record):
        return "Invalid HTTP request received" not in record.getMessage()

# Apply filter to uvicorn loggers
for logger_name in ['uvicorn.error', 'uvicorn.access', 'uvicorn']:
    uv_logger = logging.getLogger(logger_name)
    uv_logger.addFilter(InvalidHTTPFilter())

logger = logging.getLogger(__name__)
logger.info("🚀 Starting EarthFare API...")

# Import service modules (minimal - no PDF/image processing)
try:
    from app.services import csv_parser, text_processor, product_search, url_scraper, brand_voice, export_csv
    logger.info("✅ All service modules imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import service modules: {e}")
    csv_parser = text_processor = product_search = url_scraper = brand_voice = export_csv = None

# Import EarthFare-specific modules
try:
    from app.services.product_enricher import enrich_product, enrich_products
    from app.services.shopify_mapper import map_to_shopify_csv, map_products_to_shopify, SHOPIFY_CSV_HEADERS
    from app.services.dietary_detector import detect_dietary_attributes
    from app.services.nutrition_parser import parse_nutrition_from_html
    logger.info("✅ EarthFare modules imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ EarthFare modules not fully available: {e}")
    enrich_product = enrich_products = map_to_shopify_csv = None

from app.config import ALLOWED_CATEGORIES

# Configuration
API_KEY = os.getenv("DOCLING_API_KEY", "")
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"

# Create FastAPI app
app = FastAPI(
    title="Universal Product Automation",
    description="Complete product automation backend with React frontend",
    version="2.0.0"
)

# CORS Configuration - Allow Vercel frontend and local dev
# IMPORTANT: No trailing slashes on origins!
origins = [
    "https://earthfare.vercel.app",
    "https://earthfare-git-claude-earthfare-b-54053e-chris-projects-562b0f0c.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

# Add any additional origins from environment variable (comma-separated)
extra_origins = os.getenv("CORS_ORIGINS", "")
if extra_origins:
    origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

# Add CORS middleware - this MUST be before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Use specific origins for security
    allow_credentials=True,  # Allow credentials with specific origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,  # Cache preflight for 24 hours
)

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🌿 EarthFare API Started Successfully!")
    logger.info(f"📁 Frontend dir: {FRONTEND_BUILD_DIR}")
    logger.info(f"🔑 API Key configured: {bool(API_KEY)}")
    logger.info(f"🤖 OpenAI configured: {bool(os.getenv('OPENAI_API_KEY'))}")
    logger.info("=" * 50)

def check_key(x_api_key: Optional[str]):
    """Validate API key if configured"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# Models
class ProcessingResponse(BaseModel):
    success: bool
    products: List[dict]
    message: Optional[str] = None

class BrandVoiceRequest(BaseModel):
    products: List[dict]
    category: str

class TextProcessorRequest(BaseModel):
    text: str
    category: str

class ProductSearchRequest(BaseModel):
    query: str
    category: str
    search_type: str = "sku"

class URLScraperRequest(BaseModel):
    url: str
    category: str

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def merge_brand_data(products: List[dict], brand_data: List[dict]) -> List[dict]:
    """
    Merge scraped brand data with existing products

    Matches products by name (fuzzy) or barcode, then fills in missing fields
    like nutrition, ingredients, allergens from the brand website scrape.

    Args:
        products: Products parsed from CSV
        brand_data: Products scraped from brand URL

    Returns:
        Products with merged data from brand URL
    """
    if not brand_data:
        return products

    # Build lookup index from brand data by normalized name and barcode
    brand_index_by_name = {}
    brand_index_by_barcode = {}

    for item in brand_data:
        # Index by name (normalized)
        name = item.get("name", "").strip().lower()
        if name:
            # Also index by key words from name
            brand_index_by_name[name] = item
            # Index by words for fuzzy matching
            for word in name.split():
                if len(word) > 3:  # Only meaningful words
                    if word not in brand_index_by_name:
                        brand_index_by_name[word] = item

        # Index by barcode
        barcode = item.get("barcode", "") or item.get("ean", "")
        if barcode:
            brand_index_by_barcode[str(barcode).strip()] = item

    # Merge data into products
    for product in products:
        matched_brand = None

        # Try barcode match first (most reliable)
        barcode = product.get("barcode", "") or product.get("ean", "")
        if barcode and str(barcode).strip() in brand_index_by_barcode:
            matched_brand = brand_index_by_barcode[str(barcode).strip()]

        # Try name match
        if not matched_brand:
            name = product.get("name", "").strip().lower()
            if name and name in brand_index_by_name:
                matched_brand = brand_index_by_name[name]

            # Try partial name match
            if not matched_brand and name:
                for word in name.split():
                    if len(word) > 3 and word in brand_index_by_name:
                        matched_brand = brand_index_by_name[word]
                        break

        # Merge matched data (only fill missing fields)
        if matched_brand:
            # Nutrition
            if not product.get("nutrition") and matched_brand.get("nutrition"):
                product["nutrition"] = matched_brand["nutrition"]
                product["nutrition_source"] = "brand_website"

            if not product.get("nutrition_shopify") and matched_brand.get("nutrition_shopify"):
                product["nutrition_shopify"] = matched_brand["nutrition_shopify"]

            # Ingredients
            if not product.get("ingredients") and matched_brand.get("ingredients"):
                product["ingredients"] = matched_brand["ingredients"]

            # Allergens
            if not product.get("allergens") and matched_brand.get("allergens"):
                product["allergens"] = matched_brand["allergens"]

            # Dietary flags
            if not product.get("dietary") and matched_brand.get("dietary"):
                product["dietary"] = matched_brand["dietary"]

            # Description (if missing)
            if not product.get("romance_copy") and matched_brand.get("description"):
                product["romance_copy"] = matched_brand["description"]

            product["_brand_url_matched"] = True
            logger.info(f"✅ Merged brand data for: {product.get('name', 'Unknown')}")

    return products


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Root endpoint - confirms API is running"""
    return {
        "service": "EarthFare Product Automation API",
        "status": "running",
        "version": "2.0.0",
        "docs": "/docs"
    }

@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": "EarthFare API is running",
        "endpoints": [
            "/api/parse-csv",
            "/api/scrape-url",
            "/api/export-shopify",
            "/api/generate-brand-voice"
        ]
    }

@app.get("/healthz")
async def healthz():
    """Health check endpoint"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "frontend_available": FRONTEND_BUILD_DIR.exists()
    }

@app.post("/api/parse-csv")
async def parse_csv_endpoint(
    file: UploadFile = File(...),
    category: str = Form(...),
    brand_url: Optional[str] = Form(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Parse CSV file, enrich with nutrition data, and generate brand voice descriptions

    Args:
        file: CSV file with product data
        category: Product category (e.g., "Health Supplements", "Store Cupboard")
        brand_url: Optional manufacturer website URL to scrape for additional data
                   (nutrition, ingredients, etc.) - useful when OpenFoodFacts lacks data
    """
    check_key(x_api_key)

    try:
        if category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category")

        logger.info(f"📊 Processing CSV upload for category: {category}")
        if brand_url:
            logger.info(f"🔗 Brand URL provided for additional scraping: {brand_url}")

        if not csv_parser:
            raise HTTPException(status_code=503, detail="CSV parser not available")

        file_content = await file.read()
        products = await csv_parser.process(file_content, category)
        logger.info(f"✅ Parsed {len(products)} products from CSV")

        # Enrich with OpenFoodFacts nutrition data (uses barcodes from CSV)
        if enrich_products and products:
            try:
                products = await enrich_products(products, scrape=False)
                logger.info(f"✅ Enriched products with nutrition data")
            except Exception as e:
                logger.warning(f"⚠️ Enrichment failed, continuing: {e}")

        # If brand URL provided, scrape for additional product data
        if brand_url and url_scraper:
            try:
                logger.info(f"🌐 Scraping brand URL for additional data: {brand_url}")
                brand_data = await url_scraper.scrape(brand_url, category)

                # Merge scraped data with products (match by name/barcode)
                if brand_data:
                    products = merge_brand_data(products, brand_data)
                    logger.info(f"✅ Merged data from brand URL for {len(brand_data)} products")
            except Exception as e:
                logger.warning(f"⚠️ Brand URL scraping failed, continuing: {e}")

        if brand_voice:
            try:
                products = await brand_voice.generate(products, category)
                logger.info(f"✅ Brand voice generated")
            except Exception as e:
                logger.warning(f"⚠️ Brand voice failed: {e}")

        # Log data summary for debugging
        for p in products[:2]:  # Log first 2 products only
            has_ingredients = bool(p.get("ingredients"))
            has_nutrition = bool(p.get("nutrition"))
            nutrition_keys = list(p.get("nutrition", {}).keys()) if p.get("nutrition") else []
            logger.info(f"📦 Product '{p.get('name', 'Unknown')[:30]}': ingredients={has_ingredients}, nutrition={has_nutrition} {nutrition_keys}")

        return ProcessingResponse(
            success=True,
            products=products,
            message=f"Successfully processed {len(products)} products"
        )
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-text")
async def process_text_endpoint(
    request: TextProcessorRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Process free-form text"""
    check_key(x_api_key)
    
    try:
        if request.category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        if not text_processor:
            raise HTTPException(status_code=503, detail="Text processor not available")
        
        products = await text_processor.process(request.text, request.category)
        
        if brand_voice:
            products = await brand_voice.generate(products, request.category)
        
        return ProcessingResponse(success=True, products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search-product")
async def search_product_endpoint(
    request: ProductSearchRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Search for product by SKU/EAN"""
    check_key(x_api_key)
    
    try:
        if request.category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        if not product_search:
            raise HTTPException(status_code=503, detail="Product search not available")
        
        products = await product_search.search(request.query, request.category, request.search_type)
        
        if brand_voice:
            products = await brand_voice.generate(products, request.category)
        
        return ProcessingResponse(success=True, products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape-url")
async def scrape_url_endpoint(
    request: URLScraperRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Scrape URL for product data including ingredients, nutrition, and allergens"""
    check_key(x_api_key)

    try:
        if request.category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")

        if not url_scraper:
            raise HTTPException(status_code=503, detail="URL scraper not available")

        # Initial scrape for basic product data
        products = await url_scraper.scrape(request.url, request.category)

        # Enrich with ingredients, nutrition, allergens from the scraped content
        if enrich_products and products:
            logger.info(f"Enriching {len(products)} products from URL scrape...")
            try:
                products = await enrich_products(products, scrape=False)
            except Exception as enrich_err:
                logger.warning(f"Enrichment failed, continuing with basic data: {enrich_err}")

        # Generate brand voice descriptions
        if brand_voice:
            products = await brand_voice.generate(products, request.category)

        return ProcessingResponse(success=True, products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/categories")
async def get_categories():
    """Get list of allowed categories"""
    return {"categories": sorted(list(ALLOWED_CATEGORIES))}

@app.post("/api/generate-brand-voice")
async def generate_brand_voice_endpoint(
    request: BrandVoiceRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Generate brand voice descriptions for products"""
    check_key(x_api_key)
    
    try:
        if request.category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        if not brand_voice:
            raise HTTPException(status_code=503, detail="Brand voice service not available")
        
        logger.info(f"🎤 Generating brand voice for {len(request.products)} products")
        products = await brand_voice.generate(request.products, request.category)
        
        return ProcessingResponse(success=True, products=products)
    except Exception as e:
        logger.error(f"Brand voice error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export")
async def export_products_endpoint(
    request: dict,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Export enhanced products to Business Central CSV or Excel format"""
    check_key(x_api_key)
    
    try:
        products = request.get("products", [])
        format_type = request.get("format", "csv").lower()
        
        if not products:
            raise HTTPException(status_code=400, detail="No products provided")
        
        logger.info(f"📤 Exporting {len(products)} products as {format_type.upper()}")
        
        if format_type == "excel":
            file_bytes = export_csv.export_to_excel(products)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = "products_export.xlsx"
        else:
            file_bytes = export_csv.export_to_business_central(products)
            media_type = "text/csv; charset=utf-8"
            filename = "products_export.csv"
        
        from fastapi.responses import Response
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# EARTHFARE-SPECIFIC ENDPOINTS
# ============================================================

class EnrichProductRequest(BaseModel):
    products: List[dict]
    scrape_suppliers: bool = True

class ShopifyExportRequest(BaseModel):
    products: List[dict]

@app.post("/api/enrich-products")
async def enrich_products_endpoint(
    request: EnrichProductRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """
    Enrich products with nutritional data, ingredients, and dietary info
    by scraping supplier websites (CLF, Essential, Suma, Infinity)
    """
    check_key(x_api_key)

    try:
        if not enrich_products:
            raise HTTPException(status_code=503, detail="Product enrichment service not available")

        logger.info(f"🔍 Enriching {len(request.products)} products")

        enriched = await enrich_products(
            request.products,
            scrape=request.scrape_suppliers
        )

        logger.info(f"✅ Enriched {len(enriched)} products with nutritional data")

        return ProcessingResponse(
            success=True,
            products=enriched,
            message=f"Enriched {len(enriched)} products"
        )
    except Exception as e:
        logger.error(f"Enrichment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export-shopify")
async def export_shopify_endpoint(
    request: ShopifyExportRequest,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """
    Export products to Shopify/Matrixify CSV format with metafields
    """
    check_key(x_api_key)

    try:
        if not map_products_to_shopify:
            raise HTTPException(status_code=503, detail="Shopify mapper not available")

        products = request.products
        if not products:
            raise HTTPException(status_code=400, detail="No products provided")

        logger.info(f"📤 Exporting {len(products)} products to Shopify CSV")

        # Map to Shopify format
        shopify_rows = map_products_to_shopify(products)

        # Generate CSV
        import csv
        import io

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=SHOPIFY_CSV_HEADERS)
        writer.writeheader()
        writer.writerows(shopify_rows)

        csv_content = output.getvalue().encode('utf-8-sig')  # BOM for Excel compatibility

        from fastapi.responses import Response
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="earthfare_shopify_import.csv"'
            }
        )
    except Exception as e:
        logger.error(f"Shopify export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-earthfare")
async def process_earthfare_endpoint(
    file: UploadFile = File(...),
    category: str = Form(default="Store Cupboard"),
    enrich: bool = Form(default=True),
    brand_url: Optional[str] = Form(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """
    Complete EarthFare pipeline: Parse CSV -> Enrich -> Brand Voice -> Shopify CSV

    Args:
        file: CSV file with product data
        category: Product category
        enrich: Whether to enrich with supplier data
        brand_url: Optional manufacturer website URL to scrape for additional data
    """
    check_key(x_api_key)

    try:
        logger.info(f"🌿 EarthFare pipeline starting for category: {category}")
        if brand_url:
            logger.info(f"🔗 Brand URL provided: {brand_url}")

        # Step 1: Parse CSV
        if not csv_parser:
            raise HTTPException(status_code=503, detail="CSV parser not available")

        file_content = await file.read()
        products = await csv_parser.process(file_content, category)
        logger.info(f"📊 Parsed {len(products)} products")

        # Step 2: Enrich with supplier data (optional)
        if enrich and enrich_products:
            try:
                products = await enrich_products(products, scrape=True)
                logger.info(f"🔍 Enriched products with nutritional data")
            except Exception as e:
                logger.warning(f"⚠️ Enrichment failed, continuing: {e}")

        # Step 2b: Scrape brand URL for additional data (if provided)
        if brand_url and url_scraper:
            try:
                logger.info(f"🌐 Scraping brand URL: {brand_url}")
                brand_data = await url_scraper.scrape(brand_url, category)
                if brand_data:
                    products = merge_brand_data(products, brand_data)
                    logger.info(f"✅ Merged data from brand URL")
            except Exception as e:
                logger.warning(f"⚠️ Brand URL scraping failed: {e}")

        # Step 3: Generate brand voice descriptions
        if brand_voice:
            try:
                products = await brand_voice.generate(products, category)
                logger.info(f"🎤 Brand voice generated")
            except Exception as e:
                logger.warning(f"⚠️ Brand voice failed: {e}")

        return ProcessingResponse(
            success=True,
            products=products,
            message=f"Processed {len(products)} products through EarthFare pipeline"
        )
    except Exception as e:
        logger.error(f"EarthFare pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# SERVE REACT FRONTEND
# ============================================================

# Mount static files (only if static subdir exists - frontend served from Vercel)
static_dir = FRONTEND_BUILD_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"✅ Mounted static files from {static_dir}")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        """Serve React app for all non-API routes"""
        # If path starts with /api, let FastAPI handle it
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        # Check if specific file exists
        file_path = FRONTEND_BUILD_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html (SPA fallback)
        return FileResponse(FRONTEND_BUILD_DIR / "index.html")
else:
    logger.info("ℹ️ No frontend build - API-only mode (frontend served from Vercel)")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
