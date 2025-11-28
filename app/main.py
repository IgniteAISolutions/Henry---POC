from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import io

app = FastAPI(title="Product Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "product-automation"}

@app.get("/healthz")
def health():
    return {"status": "healthy"}

@app.post("/parse-csv")
async def parse_csv(file: UploadFile = File(...), category: str = Form(...)):
    """Parse CSV and return products"""
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        products = []
        for idx, row in df.iterrows():
            product = {
                "id": f"csv-{idx}",
                "name": str(row.get("name", row.get("Name", row.get("product_name", "Unknown")))),
                "sku": str(row.get("sku", row.get("SKU", row.get("code", "")))),
                "brand": str(row.get("brand", row.get("Brand", ""))),
                "category": category,
                "descriptions": {
                    "shortDescription": str(row.get("description", row.get("Description", "")))[:280],
                    "metaDescription": str(row.get("description", row.get("Description", "")))[:160],
                    "longDescription": str(row.get("description", row.get("Description", ""))),
                }
            }
            products.append(product)
        
        return {"success": True, "products": products}
    except Exception as e:
        return {"success": False, "error": str(e)}
