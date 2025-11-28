"""
Configuration management for the Elestio service.
Centralizes all environment variables and settings.
"""
import os
from typing import Optional

class Config:
    """Application configuration"""

    # Server
    PORT: int = int(os.getenv("PORT", "8080"))
    API_KEY: str = os.getenv("DOCLING_API_KEY", "")

    # Supabase (storage only)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://gxbcqiqwwidoteusipgn.supabase.co")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

    # EAN Search API
    EAN_SEARCH_API_KEY: str = os.getenv("EAN_SEARCH_API_KEY", "")
    EAN_SEARCH_API_URL: str = os.getenv("EAN_SEARCH_API_URL", "https://api.ean-search.org/api")

    # OpenAI (for brand voice)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # OCR Settings
    ENABLE_OCR: bool = os.getenv("ENABLE_OCR", "true").lower() == "true"
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "tesseract")

    # Processing limits
    MAX_FILE_SIZE_MB: int = 50
    MAX_CSV_ROWS: int = 10000
    REQUEST_TIMEOUT_SECONDS: int = 300

config = Config()

# Backwards compatible alias for settings
settings = config
