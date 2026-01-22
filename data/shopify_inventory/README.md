# Shopify Inventory Reference Data

This directory contains Earthfare's Shopify product inventory for reference during imports.

## Files

- `products_export.csv` - Full Shopify product export (add your export here)

## Purpose

1. **Product Matching** - Use Handle or Barcode to update existing products instead of creating duplicates
2. **Data Validation** - Compare generated content against live data
3. **Gap Analysis** - Identify products missing nutrition, ingredients, or icons

## How to Update

1. Export from Shopify Admin: Products > Export > All products
2. Replace `products_export.csv` with your new export
3. Commit and push the changes

## Key Fields for Matching

| Field | Purpose |
|-------|---------|
| `Handle` | Primary identifier - use for updates |
| `Variant Barcode` | EAN/UPC - matches OpenFoodFacts lookups |
| `ID` | Shopify internal ID - use for Matrixify updates |
| `Title` | Product name |
| `Vendor` | Brand name |

## Usage in Code

The inventory can be loaded for product matching:

```python
from app.utils.inventory_matcher import load_inventory, find_product

inventory = load_inventory()
existing = find_product(inventory, barcode="5060093992311")
```
