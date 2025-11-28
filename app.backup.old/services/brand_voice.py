"""
Brand Voice Generator Service
Generate brand-appropriate product descriptions using OpenAI.
"""
from openai import AsyncOpenAI
from typing import List, Dict, Any
from app.config import config
import json

class BrandVoiceGenerator:
    """Generate brand voice descriptions"""

    # Category-specific brand voice prompts
    CATEGORY_PROMPTS = {
        "Electricals": {
            "tone": "professional, technical yet accessible",
            "focus": "features, specifications, performance, ease of use",
            "style": "Clear, benefit-focused descriptions highlighting technical capabilities and user experience"
        },
        "Bakeware, Cookware": {
            "tone": "warm, inspiring, practical",
            "focus": "durability, cooking performance, ease of cleaning",
            "style": "Engaging descriptions that inspire cooking while emphasizing quality and functionality"
        },
        "Dining, Drink, Living": {
            "tone": "elegant, lifestyle-oriented",
            "focus": "aesthetics, quality, entertaining",
            "style": "Sophisticated descriptions that evoke ambiance and lifestyle enhancement"
        },
        "Knives, Cutlery": {
            "tone": "precise, quality-focused",
            "focus": "craftsmanship, materials, performance",
            "style": "Detailed descriptions emphasizing precision, quality materials, and professional-grade performance"
        },
        "Food Prep & Tools": {
            "tone": "practical, helpful",
            "focus": "efficiency, versatility, ease of use",
            "style": "Clear, practical descriptions highlighting how tools make kitchen tasks easier"
        },
        "Clothing": {
            "tone": "stylish, comfort-focused",
            "focus": "fabric, fit, style, comfort",
            "style": "Appealing descriptions balancing style and comfort"
        }
    }

    def __init__(self):
        if not config.OPENAI_API_KEY:
            print("[BrandVoice] WARNING: OPENAI_API_KEY not configured")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

    def build_prompt(self, product: Dict[str, Any], category: str) -> str:
        """Build the prompt for brand voice generation"""

        category_guide = self.CATEGORY_PROMPTS.get(
            category,
            self.CATEGORY_PROMPTS["Electricals"]  # Default
        )

        # Extract existing content
        name = product.get("name", "")
        brand = product.get("brand", "")
        raw_content = product.get("rawExtractedContent", "")
        existing_desc = product.get("descriptions", {})

        # Build context
        context_parts = []
        if brand:
            context_parts.append(f"Brand: {brand}")
        if name:
            context_parts.append(f"Product: {name}")
        if raw_content:
            context_parts.append(f"Extracted Content:\n{raw_content}")
        elif existing_desc.get("longDescription"):
            context_parts.append(f"Description:\n{existing_desc['longDescription']}")

        context = "\n".join(context_parts)

        prompt = f"""You are a professional product copywriter for an upscale kitchenware and homeware retailer.

Category: {category}
Tone: {category_guide['tone']}
Focus: {category_guide['focus']}
Style: {category_guide['style']}

Product Information:
{context}

Generate three descriptions:

1. SHORT DESCRIPTION (100-150 words, HTML format):
- 3-4 key benefits as bullet points
- Highlight main features
- Focus on what makes this product special
- Use <p> and <br> tags

2. META DESCRIPTION (140-160 characters):
- Compelling single sentence
- Include key benefit
- Enticing but factual
- No HTML tags

3. LONG DESCRIPTION (300-500 words, HTML format):
- Comprehensive overview in multiple paragraphs
- Detailed features and benefits
- Technical specifications naturally integrated
- Use cases and applications
- Build desire while remaining informative
- Use <p> tags for paragraphs

Return ONLY a JSON object with this exact structure:
{{
  "shortDescription": "<p>...</p>",
  "metaDescription": "...",
  "longDescription": "<p>...</p><p>...</p>"
}}

IMPORTANT:
- Keep HTML simple (only <p> and <br> tags)
- Make content compelling but accurate
- Maintain consistent brand voice
- Focus on benefits, not just features
- Be specific, avoid generic language"""

        return prompt

    async def generate_for_product(
        self,
        product: Dict[str, Any],
        category: str
    ) -> Dict[str, Any]:
        """
        Generate brand voice descriptions for a single product.

        Args:
            product: Product dictionary
            category: Product category

        Returns:
            Updated product with brand voice descriptions
        """
        if not self.client:
            print("[BrandVoice] OpenAI not configured, skipping")
            return product

        try:
            prompt = self.build_prompt(product, category)

            print(f"[BrandVoice] Generating for: {product.get('name')}")

            response = await self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional product copywriter. Always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1500,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            descriptions = json.loads(content)

            # Update product
            product["descriptions"] = {
                "shortDescription": descriptions.get("shortDescription", ""),
                "metaDescription": descriptions.get("metaDescription", ""),
                "longDescription": descriptions.get("longDescription", ""),
            }

            print(f"[BrandVoice] ✅ Generated for: {product.get('name')}")
            return product

        except Exception as e:
            print(f"[BrandVoice] Error generating for {product.get('name')}: {e}")
            # Return product unchanged
            return product

    async def generate_for_products(
        self,
        products: List[Dict[str, Any]],
        category: str
    ) -> List[Dict[str, Any]]:
        """
        Generate brand voice for multiple products.

        Args:
            products: List of products
            category: Product category

        Returns:
            Updated products list
        """
        print(f"[BrandVoice] Generating for {len(products)} products in category: {category}")

        enhanced_products = []
        for product in products:
            enhanced = await self.generate_for_product(product, category)
            enhanced_products.append(enhanced)

        return enhanced_products

# Singleton instance
brand_voice_generator = BrandVoiceGenerator()
