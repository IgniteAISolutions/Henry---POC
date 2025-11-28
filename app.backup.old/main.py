"""
Docling Service - FastAPI Application
Professional document processing service using Docling
"""
import logging
import time
import uuid
from pathlib import Path
from typing import Optional
import tempfile
import os

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .models import (
    HealthResponse,
    DocumentProcessingResponse,
    DocumentMetadata,
    DocumentType,
    ProcessingOptions,
    ProcessingStatus,
    ErrorResponse,
)
from .services import document_processor

# Import all product automation routers
from .routers import (
    pdf_router,
    image_router,
    sku_router,
    url_router,
    brand_voice_router,
    export_csv_router,
    seo_router,
)

# Configure logging
logging.basicConfig(
    level=settings.log_level.upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Universal Product Automation",
    description="Harts of Stur Product Automation API - Document processing, product extraction, and brand voice generation",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all product automation routers
app.include_router(pdf_router)
app.include_router(image_router)
app.include_router(sku_router)
app.include_router(url_router)
app.include_router(brand_voice_router)
app.include_router(export_csv_router)
app.include_router(seo_router)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs"""
    return {
        "service": "Universal Product Automation",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/healthz"
    }


@app.get("/healthz", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    Returns service status and availability
    """
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        docling_available=document_processor.converter is not None
    )


@app.post("/process", response_model=DocumentProcessingResponse)
async def process_document(
    file: UploadFile = File(...),
    extract_tables: bool = Form(True),
    extract_images: bool = Form(False),
    enable_ocr: bool = Form(True),
    ocr_language: str = Form("eng"),
    output_format: str = Form("markdown"),
    max_pages: Optional[int] = Form(None),
):
    """
    Process a document and extract content

    Supports: PDF, DOCX, PPTX, HTML files
    """
    job_id = str(uuid.uuid4())
    start_time = time.time()
    temp_file_path = None

    logger.info(f"[{job_id}] Processing document: {file.filename}")

    try:
        file_ext = Path(file.filename).suffix.lower().lstrip('.')
        if file_ext not in settings.allowed_extensions_list:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Allowed: {settings.allowed_extensions_list}"
            )

        file_content = await file.read()
        metadata = DocumentMetadata(
            file_name=file.filename,
            file_size_bytes=len(file_content),
            mime_type=file.content_type or "application/octet-stream",
            document_type=DocumentType(file_ext)
        )

        if len(file_content) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File size ({len(file_content)} bytes) exceeds maximum ({settings.max_file_size_bytes} bytes)"
            )

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{file_ext}",
            dir=settings.temp_dir
        ) as temp_file:
            temp_file.write(file_content)
            temp_file_path = Path(temp_file.name)

        logger.info(f"[{job_id}] Saved to temp file: {temp_file_path}")

        options = ProcessingOptions(
            extract_tables=extract_tables,
            extract_images=extract_images,
            enable_ocr=enable_ocr,
            ocr_language=ocr_language,
            output_format=output_format,
            max_pages=max_pages
        )

        extracted_text, extracted_markdown, elements, tables, page_count = \
            await document_processor.process_document(temp_file_path, metadata, options)

        processing_time = time.time() - start_time

        response = DocumentProcessingResponse(
            success=True,
            job_id=job_id,
            metadata=metadata,
            extracted_text=extracted_text,
            extracted_markdown=extracted_markdown,
            elements=elements,
            tables=tables,
            page_count=page_count,
            character_count=len(extracted_text),
            processing_time_seconds=round(processing_time, 2),
            status=ProcessingStatus.COMPLETED,
            warnings=[]
        )

        logger.info(
            f"[{job_id}] Processing completed: "
            f"{page_count} pages, {len(elements)} elements, "
            f"{len(tables)} tables in {processing_time:.2f}s"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{job_id}] Processing failed: {e}", exc_info=True)
        processing_time = time.time() - start_time

        return DocumentProcessingResponse(
            success=False,
            job_id=job_id,
            metadata=metadata if 'metadata' in locals() else None,
            extracted_text="",
            elements=[],
            tables=[],
            page_count=0,
            character_count=0,
            processing_time_seconds=round(processing_time, 2),
            status=ProcessingStatus.FAILED,
            error=str(e)
        )

    finally:
        if temp_file_path and temp_file_path.exists():
            try:
                os.unlink(temp_file_path)
                logger.debug(f"[{job_id}] Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"[{job_id}] Failed to cleanup temp file: {e}")


@app.post("/extract-text")
async def extract_text_only(file: UploadFile = File(...)):
    """
    Simple endpoint to extract only text from a document
    """
    result = await process_document(
        file=file,
        extract_tables=False,
        extract_images=False,
        enable_ocr=True,
        ocr_language="eng",
        output_format="text",
        max_pages=None
    )

    return {
        "success": result.success,
        "text": result.extracted_text,
        "character_count": result.character_count,
        "page_count": result.page_count,
        "processing_time_seconds": result.processing_time_seconds
    }


@app.post("/extract-markdown")
async def extract_markdown_only(file: UploadFile = File(...)):
    """
    Extract document as markdown
    """
    result = await process_document(
        file=file,
        extract_tables=True,
        extract_images=False,
        enable_ocr=True,
        ocr_language="eng",
        output_format="markdown",
        max_pages=None
    )

    return {
        "success": result.success,
        "markdown": result.extracted_markdown,
        "page_count": result.page_count,
        "processing_time_seconds": result.processing_time_seconds
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )


def start():
    """Start the service"""
    logger.info(f"Starting Universal Product Automation on {settings.host}:{settings.port}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Max file size: {settings.max_file_size_mb}MB")
    logger.info(f"Allowed extensions: {settings.allowed_extensions_list}")
    logger.info(f"OCR enabled: {settings.enable_ocr}")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level
    )


if __name__ == "__main__":
    start()
