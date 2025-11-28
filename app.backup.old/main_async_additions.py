# ============= ADD THESE IMPORTS AT THE TOP =============
import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from fastapi import BackgroundTasks

# ============= ADD THESE AFTER YOUR EXISTING IMPORTS =============

# Job Status Enum
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# In-memory job storage
JOBS: Dict[str, dict] = {}

# Singleton converter
CONVERTER: Optional[DocumentConverter] = None

def get_converter():
    global CONVERTER
    if CONVERTER is None:
        print("[INIT] Creating DocumentConverter instance...")
        CONVERTER = DocumentConverter()
    return CONVERTER

# ============= ADD THESE NEW ENDPOINTS =============

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
        'request': req.dict()
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
        job['status'] = JobStatus.PROCESSING
        job['progress'] = 5
        job['progress_message'] = "Downloading PDF..."
        
        start_time = time.time()
        category = req.category or "Electricals"
        
        # Download file
        tmp_path = await fetch_to_tmp(req.file_url)
        
        job['progress'] = 10
        job['progress_message'] = "PDF downloaded, converting..."
        
        try:
            converter = get_converter()
            
            job['progress'] = 20
            job['progress_message'] = "Extracting content (this may take 2-3 minutes)..."
            
            # Convert PDF
            result: ConversionResult = converter.convert(tmp_path)
            
            job['progress'] = 70
            job['progress_message'] = "Processing extracted data..."
            
            md = result.document.export_to_markdown() if req.return_markdown else None
            jj = result.document.export_to_dict() if req.return_json else None
            pages_processed = len(result.document.pages)
            
            job['progress'] = 80
            job['progress_message'] = "Extracting product information..."
            
            # Extract product fields (use your existing infer_product_fields_improved function)
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
            job['progress_message'] = "Generating brand voice..."
            
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
# ============= ADD THESE IMPORTS AT THE TOP =============
import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from fastapi import BackgroundTasks

# ============= ADD THESE AFTER YOUR EXISTING IMPORTS =============

# Job Status Enum
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# In-memory job storage
JOBS: Dict[str, dict] = {}

# Singleton converter
CONVERTER: Optional[DocumentConverter] = None

def get_converter():
    global CONVERTER
    if CONVERTER is None:
        print("[INIT] Creating DocumentConverter instance...")
        CONVERTER = DocumentConverter()
    return CONVERTER

# ============= ADD THESE NEW ENDPOINTS =============

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
        'request': req.dict()
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
        job['status'] = JobStatus.PROCESSING
        job['progress'] = 5
        job['progress_message'] = "Downloading PDF..."
        
        start_time = time.time()
        category = req.category or "Electricals"
        
        # Download file
        tmp_path = await fetch_to_tmp(req.file_url)
        
        job['progress'] = 10
        job['progress_message'] = "PDF downloaded, converting..."
        
        try:
            converter = get_converter()
            
            job['progress'] = 20
            job['progress_message'] = "Extracting content (this may take 2-3 minutes)..."
            
            # Convert PDF
            result: ConversionResult = converter.convert(tmp_path)
            
            job['progress'] = 70
            job['progress_message'] = "Processing extracted data..."
            
            md = result.document.export_to_markdown() if req.return_markdown else None
            jj = result.document.export_to_dict() if req.return_json else None
            pages_processed = len(result.document.pages)
            
            job['progress'] = 80
            job['progress_message'] = "Extracting product information..."
            
            # Extract product fields (use your existing infer_product_fields_improved function)
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
            job['progress_message'] = "Generating brand voice..."
            
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
