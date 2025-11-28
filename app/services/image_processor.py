"""
Image Processor Service
AI Vision processing for product images using OpenAI GPT-4 Vision
"""
import io
import base64
import logging
import os
from typing import List, Dict, Any
from PIL import Image
import httpx

from ..config import MAX_IMAGE_SIZE_MB, SUPPORTED_IMAGE_FORMATS

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


async def process(file_content: bytes, category: str, filename: str = "", additional_context: str = "") -> List[Dict[str, Any]]:
    """
    Process image file using AI vision to identify product and generate descriptions
    Args:
        file_content: Image file content as bytes
        category: Product category
        filename: Original filename
        additional_context: Additional text context from user
    Returns:
        List of product dictionaries
    """
    # Validate file size
    size_mb = len(file_content) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise ValueError(f"Image too large: {size_mb:.2f}MB (max {MAX_IMAGE_SIZE_MB}MB)")

    # Validate file format
    if filename:
        ext = filename.lower().split('.')[-1]
        if f".{ext}" not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(f"Unsupported image format: {ext}")

    try:
        # Load and validate image
        image = Image.open(io.BytesIO(file_content))
        
        # Convert to RGB if needed
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGB')
        
        # Resize if too large (OpenAI has limits)
        max_dimension = 2048
        if max(image.size) > max_dimension:
            ratio = max_dimension / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to base64
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Call OpenAI Vision API
        logger.info(f"Analyzing image with AI vision: {filename or 'unknown'}")
        product_data = await analyze_image_with_ai(image_base64, category, additional_context)

        return [product_data]

    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        raise ValueError(f"Image processing failed: {e}")


async def analyze_image_with_ai(image_base64: str, category: str, additional_context: str) -> Dict[str, Any]:
    """
    Use OpenAI GPT-4 Vision to analyze product image
    Args:
        image_base64: Base64 encoded image
        category: Product category
        additional_context: Additional context from user
    Returns:
        Product dictionary with AI-generated content
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured")

    # Build prompt
    context_text = f"\n\nAdditional context: {additional_context}" if additional_context else ""
    
    prompt = f"""You are analyzing a product image for an e-commerce catalog in the "{category}" category.{context_text}

Please analyze this image and provide:
1. Product name (concise, descriptive)
2. Brand (if visible)
3. Key features (5-10 bullet points)
4. Short description (2-3 sentences, benefit-focused, UK English)
5. Meta description (under 160 characters, UK English)
6. Long description (detailed, benefit-led, UK English, 3-5 paragraphs)

Important:
- Use UK English spelling (colour, favourite, etc.)
- Use sentence case (not ALL CAPS)
- Focus on benefits to the customer
- Be specific about what's visible in the image
- If you can see any text/labels, include that information

Return your response in this exact JSON format:
{{
  "name": "product name",
  "brand": "brand name or empty string",
  "features": ["feature 1", "feature 2", ...],
  "shortDescription": "short description",
  "metaDescription": "meta description",
  "longDescription": "long description"
}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.7
                }
            )
            
            if not response.is_success:
                raise ValueError(f"OpenAI API error: {response.status_code}")
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON response
            import json
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            # Build product object
            product = {
                "name": data.get("name", "Product from image"),
                "brand": data.get("brand", ""),
                "sku": "",  # Not visible in image
                "category": category,
                "features": data.get("features", []),
                "specifications": {},
                "descriptions": {
                    "shortDescription": data.get("shortDescription", ""),
                    "metaDescription": data.get("metaDescription", ""),
                    "longDescription": data.get("longDescription", "")
                }
            }
            
            return product
            
    except Exception as e:
        logger.error(f"AI vision analysis failed: {e}")
        raise ValueError(f"AI analysis failed: {e}")
