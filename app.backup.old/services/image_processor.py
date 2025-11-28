"""
Image OCR Processor Service
Extracts product information from images using OCR.
"""
import pytesseract
from PIL import Image
import cv2
import numpy as np
from typing import Dict, Any, Optional
import io
import re

class ImageProcessor:
    """Process images to extract product information"""

    def __init__(self):
        # Configure tesseract if needed
        # pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'
        pass

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR results.
        - Convert to grayscale
        - Increase contrast
        - Denoise
        """
        # Convert PIL to OpenCV
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        # Apply thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)

        # Convert back to PIL
        return Image.fromarray(denoised)

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Extract all text from image using OCR"""
        try:
            # Open image
            image = Image.open(io.BytesIO(image_bytes))

            # Preprocess
            processed = self.preprocess_image(image)

            # Perform OCR
            text = pytesseract.image_to_string(processed, lang='eng')

            return text.strip()

        except Exception as e:
            print(f"[OCR] Error: {e}")
            raise

    def parse_product_info(self, ocr_text: str) -> Dict[str, Any]:
        """
        Parse OCR text to extract product information.
        Looks for common patterns like SKU, barcode, product names, etc.
        """
        lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]

        # Initialize result
        result = {
            "name": None,
            "brand": None,
            "sku": None,
            "barcode": None,
            "description": None,
            "features": [],
        }

        # Patterns
        sku_pattern = r'\b([A-Z]{2,}\d{3,}[A-Z0-9]*)\b'
        barcode_pattern = r'\b(\d{8,13})\b'
        price_pattern = r'[£$€]\s*(\d+\.?\d*)'

        # Extract SKU
        for line in lines:
            sku_matches = re.findall(sku_pattern, line)
            if sku_matches:
                result["sku"] = sku_matches[0]
                break

        # Extract barcode
        for line in lines:
            barcode_matches = re.findall(barcode_pattern, line)
            if barcode_matches:
                # Validate length (EAN-8, EAN-13, UPC)
                for bc in barcode_matches:
                    if len(bc) in [8, 12, 13]:
                        result["barcode"] = bc
                        break
            if result["barcode"]:
                break

        # Extract product name (usually first or second line with substantial text)
        for line in lines[:5]:
            if len(line) > 10 and not re.match(r'^[\d\s\W]+$', line):
                result["name"] = line
                break

        # Extract brand (common brand keywords)
        brand_keywords = ['gastroback', 'zwilling', 'sage', 'breville', 'kitchenaid']
        for line in lines[:10]:
            line_lower = line.lower()
            for keyword in brand_keywords:
                if keyword in line_lower:
                    result["brand"] = keyword.title()
                    break
            if result["brand"]:
                break

        # Collect remaining lines as description
        description_lines = []
        for line in lines:
            # Skip lines that are just SKU, barcode, or product name
            if line == result.get("name") or line == result.get("sku"):
                continue
            if len(line) > 20:  # Meaningful content
                description_lines.append(line)

        if description_lines:
            result["description"] = " ".join(description_lines)

        return result

    def process_image(self, image_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Main processing function.

        Args:
            image_bytes: Image file content
            filename: Original filename

        Returns:
            Parsed product information
        """
        print(f"[Image] Processing {filename}")

        # Extract text
        ocr_text = self.extract_text_from_image(image_bytes)
        print(f"[Image] Extracted {len(ocr_text)} characters")

        # Parse product info
        product_info = self.parse_product_info(ocr_text)

        # Format as product
        product = {
            "id": f"image-{filename}",
            "name": product_info.get("name") or "Extracted from Image",
            "brand": product_info.get("brand", ""),
            "sku": product_info.get("sku", ""),
            "barcode": product_info.get("barcode", ""),
            "source": "image-ocr",
            "rawExtractedContent": ocr_text,  # For brand voice
            "descriptions": {
                "shortDescription": product_info.get("description", "")[:200],
                "metaDescription": product_info.get("description", "")[:160],
                "longDescription": product_info.get("description", ""),
            },
            "features": product_info.get("features", []),
        }

        print(f"[Image] Extracted product: {product['name']}")
        return product

# Singleton instance
image_processor = ImageProcessor()
