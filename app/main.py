# app/main.py - Complete Universal API with React Frontend
import os
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import service modules
try:
    from app.services import csv_parser, image_processor, text_processor, product_search, url_scraper, brand_voice, pdf_processor, export_csv
    logger.info("✅ All service modules imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import service modules: {e}")
    csv_parser = image_processor = text_processor = product_search = url_scraper = brand_voice = pdf_processor = None

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# API ENDPOINTS
# ============================================================

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
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Parse CSV file and generate brand voice descriptions"""
    check_key(x_api_key)
    
    try:
        if category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category")
        
        logger.info(f"📊 Processing CSV upload for category: {category}")
        
        if not csv_parser:
            raise HTTPException(status_code=503, detail="CSV parser not available")
        
        file_content = await file.read()
        products = await csv_parser.process(file_content, category)
        logger.info(f"✅ Parsed {len(products)} products from CSV")
        
        if brand_voice:
            try:
                products = await brand_voice.generate(products, category)
                logger.info(f"✅ Brand voice generated")
            except Exception as e:
                logger.warning(f"⚠️ Brand voice failed: {e}")
        
        return ProcessingResponse(
            success=True,
            products=products,
            message=f"Successfully processed {len(products)} products"
        )
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/parse-image")
async def parse_image_endpoint(
    file: UploadFile = File(...),
    category: str = Form(...),
    additional_text: str = Form(default=""),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Parse image via AI Vision and generate brand voice"""
    check_key(x_api_key)
    
    try:
        if category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        logger.info(f"📸 Processing image for category: {category}")
        
        if not image_processor:
            raise HTTPException(status_code=503, detail="Image processor not available")
        
        file_content = await file.read()
        products = await image_processor.process(
            file_content, 
            category, 
            file.filename,
            additional_context=additional_text
        )
        
        if brand_voice:
            try:
                products = await brand_voice.generate(products, category)
            except Exception as e:
                logger.warning(f"⚠️ Brand voice failed: {e}")
        
        return ProcessingResponse(success=True, products=products)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
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
    """Scrape URL for product data"""
    check_key(x_api_key)
    
    try:
        if request.category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        if not url_scraper:
            raise HTTPException(status_code=503, detail="URL scraper not available")
        
        products = await url_scraper.scrape(request.url, request.category)
        
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

@app.post("/api/extract-pdf-products")
async def extract_pdf_products_endpoint(
    file: UploadFile = File(...),
    category: str = Form(default="Electricals"),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    """Extract products from PDF using Docling"""
    check_key(x_api_key)
    
    try:
        if category not in ALLOWED_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        logger.info(f"📄 Processing PDF for category: {category}")
        
        if not pdf_processor:
            raise HTTPException(status_code=503, detail="PDF processor not available")
        
        file_content = await file.read()
        products = await pdf_processor.process(file_content, category)
        
        logger.info(f"✅ Extracted {len(products)} products from PDF")
        
        # Add brand voice generation (like other endpoints)
        if brand_voice and products:
            try:
                products = await brand_voice.generate(products, category)
                logger.info(f"✅ Brand voice generated for {len(products)} products")
            except Exception as e:
                logger.warning(f"⚠️ Brand voice failed: {e}")
        
        return ProcessingResponse(success=True, products=products)
            
    except Exception as e:
        logger.error(f"PDF error: {e}", exc_info=True)
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
# SERVE REACT FRONTEND
# ============================================================

# Mount static files
if FRONTEND_BUILD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BUILD_DIR / "static")), name="static")
    
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
    logger.warning("⚠️ Frontend build directory not found. Run 'cd frontend && npm run build'")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
