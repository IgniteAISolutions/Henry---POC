"""
CSV Parser Service
Handles multiple CSV formats and outputs standardized product data.
"""
import pandas as pd
import chardet
from typing import List, Dict, Any, Optional
import io
import re

class CSVParser:
    """Parse CSV files with flexible column mapping"""

    # Column name mappings (case-insensitive)
    COLUMN_MAPPINGS = {
        'sku': ['sku', 'code', 'product code', 'item code', 'article number'],
        'barcode': ['barcode', 'ean', 'upc', 'gtin', 'ean13', 'ean-13'],
        'name': ['name', 'product name', 'title', 'description', 'product', 'item name'],
        'brand': ['brand', 'manufacturer', 'make'],
        'short_description': ['short description', 'short desc', 'summary', 'brief'],
        'long_description': ['long description', 'long desc', 'description', 'details', 'full description'],
        'meta_description': ['meta description', 'meta desc', 'seo description'],
        'weight': ['weight', 'net weight', 'net weight (kg)', 'weight (kg)'],
        'price': ['price', 'retail price', 'rrp', 'cost'],
        'image': ['image', 'main image', 'photo', 'picture', 'img'],
    }

    def __init__(self):
        pass

    def detect_encoding(self, file_bytes: bytes) -> str:
        """Detect file encoding"""
        result = chardet.detect(file_bytes)
        return result['encoding'] or 'utf-8'

    def find_column(self, columns: List[str], search_terms: List[str]) -> Optional[str]:
        """Find column by searching for common variations"""
        columns_lower = [col.lower().strip() for col in columns]

        for search_term in search_terms:
            search_lower = search_term.lower()
            # Exact match
            if search_lower in columns_lower:
                return columns[columns_lower.index(search_lower)]
            # Partial match
            for col_lower, col_original in zip(columns_lower, columns):
                if search_lower in col_lower or col_lower in search_lower:
                    return col_original
        return None

    def clean_html(self, text: str) -> str:
        """Basic HTML cleaning - preserve HTML but remove excess whitespace"""
        if not text:
            return ""
        # Remove BOM
        text = text.replace('\ufeff', '')
        # Normalize whitespace but keep HTML tags
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def parse_csv(self, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Parse CSV file and return list of products.

        Args:
            file_bytes: CSV file content as bytes
            filename: Original filename

        Returns:
            List of product dictionaries
        """
        # Detect encoding
        encoding = self.detect_encoding(file_bytes)
        print(f"[CSV] Detected encoding: {encoding}")

        # Read CSV
        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding=encoding,
                dtype=str,  # Read all as strings initially
                keep_default_na=False
            )
        except Exception as e:
            print(f"[CSV] Failed with {encoding}, trying utf-8-sig")
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding='utf-8-sig',
                dtype=str,
                keep_default_na=False
            )

        print(f"[CSV] Found {len(df)} rows, {len(df.columns)} columns")
        print(f"[CSV] Columns: {df.columns.tolist()}")

        # Map columns
        column_map = {}
        for standard_name, search_terms in self.COLUMN_MAPPINGS.items():
            found_col = self.find_column(df.columns.tolist(), search_terms)
            if found_col:
                column_map[standard_name] = found_col
                print(f"[CSV] Mapped '{found_col}' → '{standard_name}'")

        # Parse products
        products = []
        for idx, row in df.iterrows():
            try:
                # Extract fields using mapped columns
                sku = row.get(column_map.get('sku', ''), '').strip()
                barcode = row.get(column_map.get('barcode', ''), '').strip()
                name = row.get(column_map.get('name', ''), 'Unnamed Product').strip()
                brand = row.get(column_map.get('brand', ''), '').strip()

                short_desc = self.clean_html(row.get(column_map.get('short_description', ''), ''))
                long_desc = self.clean_html(row.get(column_map.get('long_description', ''), ''))
                meta_desc = self.clean_html(row.get(column_map.get('meta_description', ''), ''))

                # Use short description as meta if meta is missing
                if not meta_desc and short_desc:
                    # Extract first sentence or truncate to 160 chars
                    meta_desc = short_desc[:160].strip()
                    if len(short_desc) > 160:
                        meta_desc = meta_desc.rsplit(' ', 1)[0] + '...'

                weight = row.get(column_map.get('weight', ''), '').strip()
                price = row.get(column_map.get('price', ''), '').strip()

                # Extract images (IMAGE, IMAGE 1-5)
                images = []
                image_col = column_map.get('image')
                if image_col and row.get(image_col):
                    images.append(row[image_col].strip())

                # Look for IMAGE 1, IMAGE 2, etc.
                for i in range(1, 10):
                    img_col = f"IMAGE {i}" if f"IMAGE {i}" in df.columns else f"IMAGE{i}"
                    if img_col in df.columns and row.get(img_col):
                        img_path = row[img_col].strip()
                        if img_path:
                            images.append(img_path)

                product = {
                    "id": f"csv-{filename}-{idx}",
                    "name": name,
                    "brand": brand,
                    "sku": sku,
                    "barcode": barcode,
                    "source": "csv",
                    "specifications": {
                        "weight": weight,
                        "images": images,
                    },
                    "descriptions": {
                        "shortDescription": short_desc,
                        "metaDescription": meta_desc,
                        "longDescription": long_desc,
                    },
                    "price": price if price else None,
                }

                products.append(product)

            except Exception as e:
                print(f"[CSV] Error parsing row {idx}: {e}")
                continue

        print(f"[CSV] Successfully parsed {len(products)} products")
        return products

# Singleton instance
csv_parser = CSVParser()
