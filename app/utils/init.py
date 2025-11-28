"""
Document processing service using Docling
"""
import time
import logging
from pathlib import Path
from typing import List, Tuple
import tempfile
import os

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

from ..models import (
    DocumentElement,
    TableData,
    DocumentMetadata,
    DocumentType,
    ProcessingOptions,
)
from ..config import settings

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents with Docling"""

    def __init__(self):
        """Initialize the document processor"""
        self.converter = None
        self._init_converter()

    def _init_converter(self):
        """Initialize Docling converter with pipeline options"""
        try:
            # Configure PDF pipeline options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = settings.enable_ocr
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True

            # Initialize converter
            self.converter = DocumentConverter(
                allowed_formats=[
                    InputFormat.PDF,
                    InputFormat.DOCX,
                    InputFormat.PPTX,
                    InputFormat.HTML,
                ],
                format_options={
                    InputFormat.PDF: pipeline_options,
                }
            )
            logger.info("Docling converter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docling converter: {e}")
            raise

    async def process_document(
        self,
        file_path: Path,
        metadata: DocumentMetadata,
        options: ProcessingOptions
    ) -> Tuple[str, str, List[DocumentElement], List[TableData], int]:
        """
        Process a document and extract content

        Returns:
            Tuple of (extracted_text, markdown, elements, tables, page_count)
        """
        start_time = time.time()
        logger.info(f"Processing document: {file_path}")

        try:
            # Convert document
            result = self.converter.convert(str(file_path))

            # Extract text content
            extracted_text = result.document.export_to_text()

            # Extract markdown
            extracted_markdown = result.document.export_to_markdown()

            # Extract structured elements
            elements = self._extract_elements(result)

            # Extract tables
            tables = self._extract_tables(result)

            # Get page count
            page_count = self._get_page_count(result)

            processing_time = time.time() - start_time
            logger.info(
                f"Document processed successfully in {processing_time:.2f}s: "
                f"{page_count} pages, {len(elements)} elements, {len(tables)} tables"
            )

            return extracted_text, extracted_markdown, elements, tables, page_count

        except Exception as e:
            logger.error(f"Error processing document: {e}")
            raise

    def _extract_elements(self, result) -> List[DocumentElement]:
        """Extract structured elements from document"""
        elements = []

        try:
            # Iterate through document items
            for item in result.document.iterate_items():
                element = DocumentElement(
                    type=item.label if hasattr(item, 'label') else 'text',
                    content=item.text if hasattr(item, 'text') else str(item),
                    page_number=item.prov[0].page_no if hasattr(item, 'prov') and item.prov else None,
                    metadata={}
                )
                elements.append(element)

        except Exception as e:
            logger.warning(f"Error extracting elements: {e}")

        return elements

    def _extract_tables(self, result) -> List[TableData]:
        """Extract tables from document"""
        tables = []

        try:
            # Get tables from document
            for table_item in result.document.tables:
                # Convert table to structured format
                table_data = TableData(
                    headers=[],
                    rows=[],
                    page_number=None
                )

                # Export table as markdown and parse
                table_md = table_item.export_to_markdown()
                if table_md:
                    lines = table_md.strip().split('\n')
                    if len(lines) > 2:  # At least header + separator + one row
                        # Extract headers
                        header_line = lines[0].strip('|').strip()
                        table_data.headers = [h.strip() for h in header_line.split('|')]

                        # Extract rows (skip separator line)
                        for row_line in lines[2:]:
                            if row_line.strip():
                                row = row_line.strip('|').strip()
                                table_data.rows.append([cell.strip() for cell in row.split('|')])

                if table_data.headers or table_data.rows:
                    tables.append(table_data)

        except Exception as e:
            logger.warning(f"Error extracting tables: {e}")

        return tables

    def _get_page_count(self, result) -> int:
        """Get page count from document result"""
        try:
            if hasattr(result.document, 'pages'):
                return len(result.document.pages)
            return 1
        except:
            return 1

    async def validate_file(self, file_path: Path) -> bool:
        """Validate if file can be processed"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.stat().st_size > settings.max_file_size_bytes:
            raise ValueError(
                f"File size ({file_path.stat().st_size} bytes) exceeds "
                f"maximum allowed size ({settings.max_file_size_bytes} bytes)"
            )

        return True


# Create singleton instance
document_processor = DocumentProcessingService()
