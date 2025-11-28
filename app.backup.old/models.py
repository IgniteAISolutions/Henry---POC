from pydantic import BaseModel, Field
from typing import List, Optional

class ExtractRequest(BaseModel):
    file_url: Optional[str] = None       # signed URL from Supabase or GCS
    force_full_ocr: bool = False
    page_start: int = 1                  # 1-based
    page_end: Optional[int] = None       # inclusive
    batch_size: int = 40                 # tunes for big docs
    per_batch_timeout_sec: int = 120
    return_markdown: bool = True
    return_json: bool = True
    category: Optional[str] = "Electricals"

class ProductFields(BaseModel):
    brand_name: Optional[str] = None
    product_type: Optional[str] = None
    sku_code: Optional[str] = None
    description: Optional[str] = None
    features: Optional[List[str]] = None
    tech_specifications: Optional[List[str]] = None

class ExtractResponse(BaseModel):
    pages_processed: int
    markdown: Optional[str] = None
    doc_json: Optional[dict] = None
    inferred: Optional[ProductFields] = None
    notes: Optional[List[str]] = None

from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class DocumentProcessingResponse(BaseModel):
    """
    Generic response model for document processing endpoints.
    Kept flexible so existing code can pass extra fields without breaking.
    """
    success: bool
    route: str
    products: List[Dict[str, Any]] = Field(default_factory=list)
    received: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None

    class Config:
        extra = "allow"
