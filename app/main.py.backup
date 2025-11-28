# app/main.py
import os
import json
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from docling.document_converter import DocumentConverter, ConversionResult

from app.models import ExtractRequest, ExtractResponse, ProductFields
from app.batching import make_ranges
from app.utils import fetch_to_tmp

API_KEY = os.getenv("DOCLING_API_KEY", "")
ALLOWED_CALLERS = os.getenv("ALLOWLIST_CIDRS", "")

app = FastAPI(title="Docling Service", version="1.0.0")

# ============================================
# CRITICAL: Initialize converter ONCE at startup
# ============================================
_converter: Optional[DocumentConverter] = None

def get_converter() -> DocumentConverter:
    """Singleton pattern - reuse the same converter instance"""
    global _converter
    if _converter is None:
        print("🔄 Initializing DocumentConverter (one-time setup)...")
        _converter = DocumentConverter()
        print("✅ DocumentConverter ready!")
    return _converter


# ============================================
# PRE-WARM MODELS ON STARTUP (ADD THIS HERE)
# ============================================
@app.on_event("startup")
async def startup_event():
    """Pre-load models on container startup"""
    print("🚀 Pre-warming Docling models...")
    get_converter()
    print("🎉 Models loaded and ready to serve requests!")


def check_key(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/convert", response_model=ExtractResponse)
async def convert_body(
    req: ExtractRequest,
    x_api_key_dash: Optional[str] = Header(default=None, alias="x-api-key"),
    x_api_key_under: Optional[str] = Header(default=None, alias="x_api_key", convert_underscores=False),
):
    x_api_key = x_api_key_dash or x_api_key_under
    check_key(x_api_key)

    if not req.file_url:
        raise HTTPException(status_code=400, detail="file_url is required")

    tmp_path = await fetch_to_tmp(req.file_url)

    try:
        # Use the singleton converter (already loaded at startup!)
        converter = get_converter()

        # Single-pass if no page_end provided
        if not req.page_end:
            result: ConversionResult = converter.convert(tmp_path)
            md = result.document.export_to_markdown() if req.return_markdown else None
            jj = result.document.export_to_dict() if req.return_json else None

            inferred = infer_product_fields(jj, md)
            return ExtractResponse(
                pages_processed=len(result.document.pages),
                markdown=md,
                doc_json=jj,
                inferred=inferred,
                notes=["single pass"],
            )

        # Batched conversion
        page_ranges = make_ranges(req.page_start, req.page_end, req.batch_size)
        markdown_parts: List[str] = []
        merged_json: Dict[str, Any] = {"pages": []}
        total_pages = 0

        for a, b in page_ranges:
            async def run_batch():
                sub = converter.convert(tmp_path)
                md_b = sub.document.export_to_markdown() if req.return_markdown else None
                jj_b = sub.document.export_to_dict() if req.return_json else None
                
                if jj_b and isinstance(jj_b, dict) and "pages" in jj_b:
                    all_pages = jj_b.get("pages", [])
                    if isinstance(all_pages, list):
                        filtered_pages = [
                            p for p in all_pages 
                            if isinstance(p, dict) and a <= p.get("page_no", 0) <= b
                        ]
                        jj_b["pages"] = filtered_pages
                
                return md_b, jj_b, len(sub.document.pages)

            md_b, jj_b, count = await asyncio.wait_for(
                run_batch(), timeout=req.per_batch_timeout_sec
            )
            total_pages += count

            if md_b:
                markdown_parts.append(md_b)
            if jj_b and isinstance(jj_b, dict) and "pages" in jj_b:
                merged_json["pages"].extend(jj_b["pages"])

        md_all = "\n\n".join(markdown_parts) if markdown_parts else None
        jj_all: Optional[dict] = merged_json if merged_json.get("pages") else None

        inferred = infer_product_fields(jj_all, md_all)
        return ExtractResponse(
            pages_processed=total_pages,
            markdown=md_all,
            doc_json=jj_all,
            inferred=inferred,
            notes=[f"processed {len(page_ranges)} ranges"],
        )
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def infer_product_fields(doc_json: Optional[dict], markdown: Optional[str]) -> Optional[ProductFields]:
    """Robust extractor that never throws."""
    if doc_json is None and not markdown:
        return None

    if isinstance(doc_json, dict):
        jj: Dict[str, Any] = doc_json
    elif isinstance(doc_json, str):
        try:
            jj = json.loads(doc_json)
        except Exception:
            jj = {}
    else:
        jj = {}

    pages = jj.get("pages", []) if isinstance(jj, dict) else []
    text_chunks: List[str] = []

    if isinstance(markdown, str) and markdown.strip():
        text_chunks.append(markdown)

    for p in pages:
        if isinstance(p, dict):
            blocks = p.get("blocks")
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        t = b.get("text")
                        if isinstance(t, str):
                            text_chunks.append(t)
                    elif isinstance(b, str):
                        text_chunks.append(b)

            page_text = p.get("text")
            if isinstance(page_text, str):
                text_chunks.append(page_text)

        elif isinstance(p, list):
            for b in p:
                if isinstance(b, dict):
                    t = b.get("text")
                    if isinstance(t, str):
                        text_chunks.append(t)
                elif isinstance(b, str):
                    text_chunks.append(b)

        elif isinstance(p, str):
            text_chunks.append(p)

    if not text_chunks and isinstance(jj, dict) and isinstance(jj.get("text"), str):
        text_chunks.append(jj["text"])

    blob = "\n".join(t for t in text_chunks if isinstance(t, str))

    inferred_up = jj.get("inferred") if isinstance(jj, dict) and isinstance(jj.get("inferred"), dict) else None

    brand = inferred_up.get("brand_name") if inferred_up else None
    if not brand and inferred_up:
        brand = inferred_up.get("brand")

    sku = inferred_up.get("sku_code") if inferred_up else None
    if not sku and inferred_up:
        sku = inferred_up.get("sku") or inferred_up.get("SKU")

    product_type = inferred_up.get("product_type") if inferred_up else None
    description = inferred_up.get("description") if inferred_up else None
    if not description and inferred_up:
        description = inferred_up.get("summary")

    features = inferred_up.get("features") if inferred_up and isinstance(inferred_up.get("features"), list) else None
    tech_specs = inferred_up.get("tech_specifications") if inferred_up and isinstance(inferred_up.get("tech_specifications"), list) else None

    if not description and blob:
        description = blob.strip()[:500]

    return ProductFields(
        brand_name=brand or None,
        product_type=product_type or None,
        sku_code=sku or None,
        description=description or None,
        features=features or None,
        tech_specifications=tech_specs or None,
    )
