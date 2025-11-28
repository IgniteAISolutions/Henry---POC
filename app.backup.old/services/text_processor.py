"""
Free Text Processor Service
Process free-form text to extract product information.
"""
from typing import Dict, Any
import re

class TextProcessor:
    """Process free text input"""

    def __init__(self):
        pass

    def extract_structured_data(self, text: str) -> Dict[str, Any]:
        """
        Try to extract structured information from free text.
        Looks for common patterns like:
        - SKU: XXX
        - Name: XXX
        - Price: XXX
        etc.
        """
        lines = text.split('\n')

        result = {
            "name": None,
            "brand": None,
            "sku": None,
            "price": None,
            "description": None,
        }

        # Patterns for structured data
        patterns = {
            "sku": r'(?:SKU|Code|Article)[:\s]+([A-Z0-9-]+)',
            "price": r'(?:Price|Cost)[:\s]+[£$€]?\s*(\d+\.?\d*)',
            "brand": r'(?:Brand|Manufacturer)[:\s]+(.+)',
        }

        structured_lines = []
        description_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to match structured patterns
            matched = False
            for key, pattern in patterns.items():
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    result[key] = match.group(1).strip()
                    structured_lines.append(line)
                    matched = True
                    break

            if not matched:
                description_lines.append(line)

        # If no name found, use first description line or first line
        if not result["name"]:
            if description_lines:
                result["name"] = description_lines[0]
            else:
                result["name"] = lines[0] if lines else "Product from Text"

        # Join remaining lines as description
        result["description"] = " ".join(description_lines)

        return result

    def process_text(self, text: str) -> Dict[str, Any]:
        """
        Process free text input.

        Args:
            text: Free-form text describing a product

        Returns:
            Product information
        """
        print(f"[Text] Processing {len(text)} characters")

        # Extract structured data
        extracted = self.extract_structured_data(text)

        # Format as product
        product = {
            "id": f"text-{hash(text)}",
            "name": extracted.get("name", "Product from Text"),
            "brand": extracted.get("brand", ""),
            "sku": extracted.get("sku", ""),
            "source": "free-text",
            "rawExtractedContent": text,  # For brand voice
            "descriptions": {
                "shortDescription": extracted.get("description", "")[:200],
                "metaDescription": extracted.get("description", "")[:160],
                "longDescription": extracted.get("description", ""),
            },
            "price": extracted.get("price"),
        }

        print(f"[Text] Extracted product: {product['name']}")
        return product

# Singleton instance
text_processor = TextProcessor()
