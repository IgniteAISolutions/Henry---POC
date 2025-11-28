"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    """Supported document types"""
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    HTML = "html"
    TXT = "txt"


class ProcessingStatus(str, Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    docling_available: bool = True


class DocumentMetadata(BaseModel):
    """Document metadata"""
    file_name: str
    file_size_bytes: int
    mime_type: str
    document_type: DocumentType
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentElement(BaseModel):
    """A single extracted document element"""
    type: str  # text, table, image, heading, etc.
    content: str
    page_number: Optional[int] = None
    confidence: Optional[float] = None
    bbox: Optional[List[float]] = None  # [x1, y1, x2, y2]
    metadata: Optional[Dict[str, Any]] = None


class TableData(BaseModel):
    """Structured table data"""
    headers: List[str]
    rows: List[List[str]]
    page_number: Optional[int] = None


class ProcessingOptions(BaseModel):
    """Options for document processing"""
    extract_tables: bool = True
    extract_images: bool = False
    enable_ocr: bool = True
    ocr_language: str = "eng"
    output_format: str = "markdown"  # markdown, json, text
    max_pages: Optional[int] = None


class DocumentProcessingRequest(BaseModel):
    """Request for document processing"""
    options: Optional[ProcessingOptions] = ProcessingOptions()


class DocumentProcessingResponse(BaseModel):
    """Response from document processing"""
    success: bool
    job_id: str
    metadata: DocumentMetadata
    extracted_text: str
    extracted_markdown: Optional[str] = None
    elements: List[DocumentElement] = []
    tables: List[TableData] = []
    page_count: int
    character_count: int
    processing_time_seconds: float
    status: ProcessingStatus = ProcessingStatus.COMPLETED
    error: Optional[str] = None
    warnings: List[str] = []


class ProductExtraction(BaseModel):
    """Product information extracted from document"""
    sku: Optional[str] = None
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    features: List[str] = []
    specifications: Dict[str, str] = {}
    price: Optional[str] = None
    confidence: float = 0.0


class ProductExtractionResponse(BaseModel):
    """Response for product extraction"""
    success: bool
    products: List[ProductExtraction] = []
    total_products: int
    processing_time_seconds: float
    source_document: str
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


# ===== Universal Product Automation Models =====


class Product(BaseModel):
    """Universal product model for Harts of Stur"""
    sku: Optional[str] = None
    barcode: Optional[str] = ""
    name: str
    rawName: Optional[str] = None
    brand: Optional[str] = "Unknown"
    category: str = "General"
    description: Optional[str] = ""
    extracted_description: Optional[str] = ""
    features: List[str] = []
    specifications: Dict[str, Any] = {}
    colors: List[str] = []
    materials: List[str] = []
    price: Optional[str] = None
    weight_kg: Optional[str] = ""
    weight_grams: Optional[int] = None
    weight_human: Optional[str] = ""
    confidence: float = 0.8
    extraction_method: Optional[str] = None
    processed_at: Optional[str] = None
    source_url: Optional[str] = None
    ocr_text: Optional[str] = None
    ocr_confidence: Optional[str] = None


class BrandVoiceDescriptions(BaseModel):
    """Brand voice generated descriptions"""
    metaDescription: str = ""
    shortDescription: str = ""
    longDescription: str = ""


class ProcessedProduct(BaseModel):
    """Product with brand voice descriptions"""
    id: str
    sku: Optional[str] = None
    barcode: Optional[str] = ""
    name: str
    brand: str = "Unknown"
    category: str = "General"
    specifications: Dict[str, Any] = {}
    features: List[str] = []
    descriptions: Optional[BrandVoiceDescriptions] = None
    weight_grams: Optional[int] = None
    weight_human: Optional[str] = ""


class PDFExtractionRequest(BaseModel):
    """Request for PDF product extraction"""
    # File is uploaded via multipart/form-data
    pass


class PDFExtractionResponse(BaseModel):
    """Response from PDF extraction"""
    success: bool
    data: Dict[str, Any]
    extracted_count: int
    source: str = "Universal PDF Analysis"
    processing_summary: Dict[str, Any]


class ImageExtractionRequest(BaseModel):
    """Request for image OCR extraction"""
    image: Optional[str] = None  # base64 encoded
    imageBase64: Optional[str] = None  # alternative field name


class ImageExtractionResponse(BaseModel):
    """Response from image extraction"""
    success: bool
    products: List[Product]


class SKUSearchRequest(BaseModel):
    """Request for SKU search"""
    sku: str


class SKUSearchResponse(BaseModel):
    """Response from SKU search"""
    success: bool
    products: List[Product]


class URLScrapeRequest(BaseModel):
    """Request for URL scraping"""
    url: str


class URLScrapeResponse(BaseModel):
    """Response from URL scraping"""
    success: bool
    products: List[Product]


class BrandVoiceRequest(BaseModel):
    """Request for brand voice generation"""
    products: Optional[List[Dict[str, Any]]] = None
    productData: Optional[Dict[str, Any]] = None
    category: Optional[str] = None


class BrandVoiceResponse(BaseModel):
    """Response from brand voice generation"""
    success: bool
    products: List[ProcessedProduct]


class ExportCSVRequest(BaseModel):
    """Request for CSV export"""
    products: List[Dict[str, Any]]


class ExportCSVResponse(BaseModel):
    """Response is a CSV file download"""
    pass
