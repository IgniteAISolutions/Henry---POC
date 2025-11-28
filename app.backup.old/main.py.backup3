# app/main.py - ASYNC VERSION WITH JOB TRACKING
# Keeps all original endpoints, adds async processing for long-running PDFs
# Flow: React → Elestio (async for PDFs) → Supabase brand-voice → React

import os
import json
import asyncio
import httpx
import re
import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from docling.document_converter import DocumentConverter, ConversionResult

from app.models import ExtractRequest, ExtractResponse, ProductFields
from app.batching import make_ranges
from app.utils import fetch_to_tmp

# Configuration
API_KEY = os.getenv("DOCLING_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://gxbcqiqwwidoteusipgn.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd4YmNxaXF3d2lkb3RldXNpcGduIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI5MDcxNzAsImV4cCI6MjA2ODQ4MzE3MH0.A2sqSV_8sAMQB9bcy0Oq5JTwuZ0nmniEn7EfGvbgZnk")

app = FastAPI(title="Docling Service", version="2.0.0")

# CORS middleware - allows React to call from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job Status Enum
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# In-memory job storage (in production, use Redis or database)
JOBS: Dict[str, dict] = {}

# Pre-initialize converter (singleton pattern for performance)
CONVERTER: Optional[DocumentConverter] = None

def get_converter():
    global CONVERTER
    if CONVERTER is None:
        print("[INIT] Creating DocumentConverter instance...")
        CONVERTER = DocumentConverter()
    return CONVERTER

# Cleanup old jobs periodically
async def cleanup_old_jobs():
    """Remove jobs older than 1 hour"""
    while True:
        now = datetime.now()
        to_remove = []
        for job_id, job in JOBS.items():
            if (now - job['created_at']).seconds > 3600:
                to_remove.append(job_id)
        for job_id in to_remove:
            del JOBS[job_id]
        await asyncio.sleep(300)  # Check every 5 minutes

# Start cleanup task on startup
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_old_jobs())


def check_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "jobs_in_queue": len([j for j in JOBS.values() if j['status'] == JobStatus.PENDING]),
        "jobs_processing": len([j for j in JOBS.values() if j['status'] == JobStatus.PROCESSING]),
        "total_jobs": len(JOBS)
    }


# ============================================================
# NEW ASYNC ENDPOINTS FOR LONG-RUNNING JOBS
# ============================================================

@app.post("/convert/async")
async def start_conversion(
    req: ExtractRequest,
    background_tasks: BackgroundTasks,
    x_api_key_dash: Optional[str] = Header(default=None, alias="x-api-key"),
    x_api_key_under: Optional[str] = Header(default=None, alias="x_api_key", convert_underscores=False),
):
    """Start async PDF processing - returns job_id immediately"""
    x_api_key = x_api_key_dash or x_api_key_under
    check_key(x_api_key)

    if not req.file_url:
        raise HTTPException(status_code=400, detail="file_url is required")

    # Create job
    job_id = str(uuid.uuid4())
    job = {
        'id': job_id,
        'status': JobStatus.PENDING,
        'created_at': datetime.now(),
        'progress': 0,
        'progress_message': "Job created, waiting to start...",
        'result': None,
        'error': None,
        'request': req.dict()  # Store request for processing
    }
    
    JOBS[job_id] = job
    
    # Start processing in background
    background_tasks.add_task(process_pdf_job, job_id)
    
    print(f"[ASYNC] Created job {job_id}")
    
    return {
        "success": True,
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "message": "Processing started. Poll /convert/status/{job_id} for updates."
    }


@app.get("/convert/status/{job_id}")
async def get_job_status(job_id: str):
    """Check status of async job"""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    
    response = {
        "job_id": job_id,
        "status": job['status'],
        "progress": job['progress'],
        "progress_message": job.get('progress_message', ''),
        "created_at": job['created_at'].isoformat()
    }
    
    # If completed, include result
    if job['status'] == JobStatus.COMPLETED:
        response['result'] = job['result']
    
    # If failed, include error
    elif job['status'] == JobStatus.FAILED:
        response['error'] = job['error']
    
    return response


async def process_pdf_job(job_id: str):
    """Process PDF in background"""
    print(f"[JOB {job_id}] Starting background processing...")
    
    job = JOBS[job_id]
    req = ExtractRequest(**job['request'])
    
    try:
        # Update status
        job['status'] = JobStatus.PROCESSING
        job['progress'] = 5
        job['progress_message'] = "Downloading PDF..."
        
        start_time = time.time()
        
        # Get category
        category = req.category or "Electricals"
        
        # Download file
        tmp_path = await fetch_to_tmp(req.file_url)
        
        job['progress'] = 10
        job['progress_message'] = "PDF downloaded, initializing converter..."
        
        try:
            # Get converter
            converter = get_converter()
            
            job['progress'] = 20
            job['progress_message'] = "Starting PDF extraction (this may take 2-3 minutes)..."
            
            print(f"[JOB {job_id}] Converting PDF...")
            
            # Convert PDF - Handle both simple and batched
            if not req.page_end:
                result: ConversionResult = converter.convert(tmp_path)
                md = result.document.export_to_markdown() if req.return_markdown else None
                jj = result.document.export_to_dict() if req.return_json else None
                pages_processed = len(result.document.pages)
            else:
                # Batched conversion
                page_ranges = make_ranges(req.page_start, req.page_end, req.batch_size)
                markdown_parts: List[str] = []
                merged_json: Dict[str, Any] = {"pages": []}
                total_pages = 0

                for a, b in page_ranges:
                    job['progress_message'] = f"Processing pages {a}-{b}..."
                    
                    sub = converter.convert({"path": tmp_path, "page_range": [a, b]})
                    md_b = sub.document.export_to_markdown() if req.return_markdown else None
                    jj_b = sub.document.export_to_dict() if req.return_json else None
                    total_pages += len(sub.document.pages)

                    if md_b:
                        markdown_parts.append(md_b)
                    if jj_b and isinstance(jj_b, dict) and "pages" in jj_b:
                        merged_json["pages"].extend(jj_b["pages"])

                md = "\n\n".join(markdown_parts) if markdown_parts else None
                jj = merged_json if merged_json.get("pages") else None
                pages_processed = total_pages
            
            job['progress'] = 70
            job['progress_message'] = "Extraction complete, processing content..."
            
            print(f"[JOB {job_id}] Processed {pages_processed} pages")
            
            job['progress'] = 80
            job['progress_message'] = "Extracting product information..."
            
            # Extract product fields
            inferred = infer_product_fields_improved(jj, md)
            
            # Build product
            product = {
                "id": os.urandom(16).hex(),
                "name": inferred.get("product_name") or "Extracted Product",
                "brand": inferred.get("brand_name", ""),
                "sku": inferred.get("sku_code", ""),
                "category": category,
                "source": "docling",
                "rawExtractedContent": md or inferred.get("description", ""),
                "specifications": {
                    "model": inferred.get("model_number", ""),
                    "variants": inferred.get("variants", []),
                    "all_skus": inferred.get("all_skus", []),
                    "prices": inferred.get("prices", {}),
                    "dimensions": inferred.get("dimensions", ""),
                    "weight": inferred.get("weight", ""),
                    "power": inferred.get("power", ""),
                    "pages_processed": pages_processed,
                    "processing_time_seconds": round(time.time() - start_time, 1),
                },
                "features": inferred.get("features", []),
                "descriptions": {
                    "shortDescription": inferred.get("summary", ""),
                    "metaDescription": inferred.get("summary", "")[:160] if inferred.get("summary") else "",
                    "longDescription": md or inferred.get("description", ""),
                }
            }
            
            job['progress'] = 90
            job['progress_message'] = "Generating brand voice descriptions..."
            
            # Call brand voice
            try:
                enhanced_products = await call_brand_voice([product], category)
                products = enhanced_products
            except Exception as e:
                print(f"[JOB {job_id}] Brand voice failed: {e}")
                products = [product]
            
            # Success!
            job['status'] = JobStatus.COMPLETED
            job['progress'] = 100
            job['progress_message'] = "Processing complete!"
            job['result'] = {
                "success": True,
                "products": products,
                "pages_processed": pages_processed,
                "processing_time_seconds": round(time.time() - start_time, 1),
            }
            
            print(f"[JOB {job_id}] ✅ Completed in {round(time.time() - start_time, 1)}s")
            
        finally:
            try:
                os.remove(tmp_path)
            except:
                pass
                
    except Exception as e:
        print(f"[JOB {job_id}] ❌ Failed: {e}")
        job['status'] = JobStatus.FAILED
        job['error'] = str(e)
        job['progress_message'] = f"Processing failed: {str(e)}"


# ============================================================
# ORIGINAL SYNCHRONOUS ENDPOINT (for backwards compatibility)
# BUT NOW WARNS ABOUT USING ASYNC FOR LARGE FILES
# ============================================================

@app.post("/convert")
async def convert_body(
    req: ExtractRequest,
    x_api_key_dash: Optional[str] = Header(default=None, alias="x-api-key"),
    x_api_key_under: Optional[str] = Header(default=None, alias="x_api_key", convert_underscores=False),
):
    """
    Original sync endpoint - kept for backwards compatibility
    NOTE: For PDFs that take >60 seconds, use /convert/async instead
    """
    x_api_key = x_api_key_dash or x_api_key_under
    check_key(x_api_key)

    if not req.file_url:
        raise HTTPException(status_code=400, detail="file_url is required")

    # Get category from request
    category = getattr(req, 'category', None) or "Electricals"

    # For large PDFs, recommend async
    print("[CONVERT] ⚠️ Note: For large PDFs, consider using /convert/async to avoid timeouts")

    tmp_path = await fetch_to_tmp(req.file_url)

    try:
        converter = get_converter()

        # Convert PDF
        if not req.page_end:
            result: ConversionResult = converter.convert(tmp_path)
            md = result.document.export_to_markdown() if req.return_markdown else None
            jj = result.document.export_to_dict() if req.return_json else None
            pages_processed = len(result.document.pages)
        else:
            # Batched conversion
            page_ranges = make_ranges(req.page_start, req.page_end, req.batch_size)
            markdown_parts: List[str] = []
            merged_json: Dict[str, Any] = {"pages": []}
            total_pages = 0

            for a, b in page_ranges:
                async def run_batch():
                    sub = converter.convert({"path": tmp_path, "page_range": [a, b]})
                    md_b = sub.document.export_to_markdown() if req.return_markdown else None
                    jj_b = sub.document.export_to_dict() if req.return_json else None
                    return md_b, jj_b, len(sub.document.pages)

                md_b, jj_b, count = await asyncio.wait_for(
                    run_batch(), timeout=req.per_batch_timeout_sec
                )
                total_pages += count

                if md_b:
                    markdown_parts.append(md_b)
                if jj_b and isinstance(jj_b, dict) and "pages" in jj_b:
                    merged_json["pages"].extend(jj_b["pages"])

            md = "\n\n".join(markdown_parts) if markdown_parts else None
            jj = merged_json if merged_json.get("pages") else None
            pages_processed = total_pages

        # Extract product fields
        inferred = infer_product_fields_improved(jj, md)

        # Build product object
        product = {
            "id": os.urandom(16).hex(),
            "name": inferred.get("product_name") or "Extracted Product",
            "brand": inferred.get("brand_name", ""),
            "sku": inferred.get("sku_code", ""),
            "category": category,
            "source": "docling",
            "rawExtractedContent": md or inferred.get("description", ""),
            "specifications": {
                "model": inferred.get("model_number", ""),
                "variants": inferred.get("variants", []),
                "prices": inferred.get("prices", {}),
                "dimensions": inferred.get("dimensions", ""),
                "weight": inferred.get("weight", ""),
                "power": inferred.get("power", ""),
                "pages_processed": pages_processed,
            },
            "features": inferred.get("features", []),
            "descriptions": {
                "shortDescription": inferred.get("summary", ""),
                "metaDescription": inferred.get("summary", "")[:160] if inferred.get("summary") else "",
                "longDescription": md or inferred.get("description", ""),
            }
        }

        # Call Supabase brand-voice
        try:
            enhanced_products = await call_brand_voice([product], category)
            return {
                "success": True,
                "products": enhanced_products,
                "pages_processed": pages_processed,
                "markdown": md,
                "inferred": inferred,
            }
        except Exception as e:
            print(f"[WARNING] Brand voice failed: {e}")
            return {
                "success": True,
                "products": [product],
                "pages_processed": pages_processed,
                "markdown": md,
                "inferred": inferred,
                "notes": ["brand_voice_unavailable"]
            }

    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


async def call_brand_voice(products: List[dict], category: str) -> List[dict]:
    """Call Supabase generate-brand-voice edge function with enhanced context"""
    brand_voice_url = f"{SUPABASE_URL}/functions/v1/generate-brand-voice"
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            brand_voice_url,
            headers={
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={
                "products": products,
                "category": category,
                "extractionHints": {
                    "useRawContent": True,
                    "preserveProductName": True,
                    "preserveBrand": True,
                    "preserveSKU": True,
                }
            }
        )
        
        if not response.is_success:
            raise Exception(f"Brand voice failed: {response.status_code}")
        
        result = response.json()
        if not result.get("success"):
            raise Exception(result.get("error", "Unknown error"))
        
        return result.get("products", products)


def infer_product_fields_improved(doc_json: Optional[dict], markdown: Optional[str]) -> Optional[dict]:
    """
    IMPROVED: Extract product fields with better logic
    """
    if doc_json is None and not markdown:
        return None

    # Get full text
    all_text = ""
    if isinstance(markdown, str) and markdown.strip():
        all_text = markdown
    
    if not all_text:
        return {
            "product_name": None,
            "brand_name": None,
            "sku_code": None,
            "description": None,
            "features": [],
        }

    lines = all_text.split("\n")
    
    # Initialize extraction results
    product_name = None
    brand_name = None
    model_number = None
    sku_codes = []
    variants = []
    prices = {}
    features = []
    dimensions = None
    weight = None
    power = None
    summary = None

    # STEP 1: Extract Brand (usually in header or logo alt text)
    for i, line in enumerate(lines[:10]):
        line_clean = line.strip().replace("#", "").strip()
        if not line_clean or len(line_clean) < 2:
            continue
        
        # Common brand patterns
        if re.match(r'^[A-Z][a-z]+$', line_clean) or re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', line_clean):
            if not brand_name and len(line_clean) < 30:
                brand_name = line_clean
                break

    # STEP 2: Extract Product Name
    for i, line in enumerate(lines[:30]):
        line_clean = line.strip().replace("#", "").strip()
        line_lower = line_clean.lower()
        
        if not line_clean or "product technical" in line_lower or "spec" in line_lower:
            continue
        if line_clean.startswith("•") or line_clean.startswith("-"):
            continue
        if re.match(r'^\d', line_clean):
            continue
            
        if any(indicator in line_lower for indicator in ["the ", "™", "®", "barista", "espresso", "machine", "coffee", "grill"]):
            if not product_name and 5 < len(line_clean) < 100:
                product_name = line_clean
                break

    # STEP 3: Extract Model Number
    model_pattern = r'\b[A-Z]{2,}[0-9]{2,}\b'
    for line in lines[:50]:
        matches = re.findall(model_pattern, line)
        if matches and not model_number:
            model_number = matches[0]
            break

    # STEP 4: Extract SKU Codes
    sku_pattern = r'\b[A-Z]{2,}[0-9]{3,}[A-Z0-9]{5,}\b'
    for line in lines:
        matches = re.findall(sku_pattern, line)
        for match in matches:
            if match not in sku_codes:
                sku_codes.append(match)

    # STEP 5: Extract Variants/Colors
    color_keywords = ["stainless steel", "black", "white", "brushed", "truffle", "nougat", "salt"]
    for line in lines:
        line_lower = line.lower()
        for color in color_keywords:
            if color in line_lower and len(line) < 100:
                variant_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+([A-Z]{3})\s+', line)
                if variant_match:
                    variant_name = variant_match.group(1)
                    variant_code = variant_match.group(2)
                    if variant_name not in [v.get("name") for v in variants]:
                        variants.append({"name": variant_name, "code": variant_code})

    # STEP 6: Extract Prices
    price_pattern = r'(GBP|EUR|USD|\$|£|€)\s*[£$€]?\s*(\d{1,5}(?:[.,]\d{2})?)'
    for line in lines[:50]:
        matches = re.findall(price_pattern, line)
        for currency, amount in matches:
            amount_clean = amount.replace(",", "")
            if currency not in prices:
                prices[currency] = amount_clean

    # STEP 7: Extract Features
    for line in lines:
        line_clean = line.strip()
        if line_clean.startswith("•") or line_clean.startswith("-"):
            feature_text = line_clean.lstrip("•-").strip()
            if 10 < len(feature_text) < 200:
                features.append(feature_text)

    # STEP 8: Generate summary
    for line in lines[:50]:
        line_clean = line.strip().replace("#", "").strip()
        if 30 < len(line_clean) < 200 and not line_clean.startswith("•"):
            if not any(skip in line_clean.lower() for skip in ["product", "technical", "spec", "dimension"]):
                summary = line_clean
                break

    return {
        "product_name": product_name,
        "brand_name": brand_name,
        "model_number": model_number,
        "sku_code": sku_codes[0] if sku_codes else None,
        "all_skus": sku_codes,
        "variants": variants,
        "prices": prices,
        "dimensions": dimensions,
        "weight": weight,
        "power": power,
        "features": features[:10],
        "summary": summary,
        "description": all_text[:1000],
    }
