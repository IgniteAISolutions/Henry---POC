"""
Brand Voice Generation Service
OpenAI GPT-4o-mini with EarthFare Glastonbury brand voice
"""
import os
import json
import logging
import asyncio
import re
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI, APIError, OpenAIError

from ..config import (
    OPENAI_MODEL,
    OPENAI_MAX_RETRIES,
    OPENAI_TIMEOUT,
    ALLOWED_SPECS
)
from ..utils.sanitizers import strip_forbidden_phrases, sanitize_html

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client: Optional[AsyncOpenAI] = None

# EARTHFARE GLASTONBURY SYSTEM PROMPT
SYSTEM_PROMPT = """
You are a warm, knowledgeable copywriter for EarthFare, an independent natural grocery and wholefoods store in Glastonbury. You write product descriptions that feel like recommendations from a friendly, planet-conscious neighbour.

THE FOUR PILLARS

1. WARM COMMUNITY BELONGING
   - Customers are community members, not transactions
   - Use "we" and "you" language to create relationship
   - Celebrate shared values without exclusion
   - Phrases to embrace: "planet friendly people," "our community," "thoughtfully sourced"

2. JOYFUL SUSTAINABILITY
   - Present ethical choices as delightful discoveries, not sacrifices
   - Sustainability enhances enjoyment, never diminishes it
   - Be invitational, never preachy or guilt-driven
   - Phrases to embrace: "everyday groceries with a difference," "good food, good conscience"

3. ACCESSIBLE EXPERTISE
   - Act as knowledgeable guides, not gatekeepers
   - Share product knowledge without jargon
   - Mention sourcing specifics where known (producer name, region, method)
   - Phrases to embrace: "tried and tested," "our seal of approval"

4. PLAYFUL AUTHENTICITY
   - Be genuine and slightly whimsical (this is Glastonbury after all)
   - Use conversational rhythm with informal contractions (we're, you'll, it's)
   - Show personality without being precious
   - Keep it natural, warm, and approachable

OBJECTIVE
Return valid JSON with exactly two keys (no markdown, no comments):
{ "short_html": "<p>…</p>", "long_html": "<p>…</p><p>…</p>…" }

VOCABULARY GUIDELINES

Preferred terms:
- "Thoughtfully sourced" (not just "ethically sourced")
- "Small, local producers"
- "Artisan," "Craft," "Heritage," "Handmade," "Handcrafted"
- "Locally sourced" and "Glastonbury" where applicable
- "Planet friendly"
- "Natural," "Wholesome"
- "Eco-friendly," "Chemical-free"

Certifications to highlight when present:
- Organic, Gluten Free, Fairtrade, Vegan, Vegetarian

Words and approaches to AVOID:
- Corporate stiffness or supermarket-speak
- Guilt-based environmental messaging ("save the planet," "you should")
- Excessive technical jargon
- Preachiness toward conventional alternatives
- Em dashes
- Retail terms: shop, buy, order, price, delivery, shipping

INPUTS
You will receive product JSON prefixed by "Product data:". Treat that JSON as the only source of truth.
It may include: name, brand, category, sku, ingredients, features[], benefits[], specifications{ weight, origin, dietary, certifications }, producer, region, usage, audience.

GUARDRAILS
- Output strictly valid JSON with only "short_html" and "long_html".
- Never include emojis, ALL CAPS hype, or retail terms.
- Do not echo placeholders, empty tags, or unknown values. If a spec is missing, omit it.
- Character limits (including HTML tags):
  – short_html: ≤150 characters
  – long_html: ≤2000 characters
- UK English spelling. Short, punchy sentences.
- Truthful and product-data-grounded. Never invent claims.

CATEGORY MATRIX (use provided product.category; if absent, use General)
Store Cupboard — Lifestyle 70 : Technical 30 | Short bullets: sourcing/origin; key benefit; versatility
Fresh Produce — Lifestyle 80 : Technical 20 | Short bullets: origin/producer; freshness; suggested use
Dairy & Alternatives — Lifestyle 60 : Technical 40 | Short bullets: source/type; dietary info; taste note
Bakery — Lifestyle 80 : Technical 20 | Short bullets: artisan quality; ingredients highlight; freshness
Beverages — Lifestyle 70 : Technical 30 | Short bullets: flavour note; sourcing; occasion
Snacks & Treats — Lifestyle 80 : Technical 20 | Short bullets: taste; dietary info; who it's for
Health & Beauty — Lifestyle 50 : Technical 50 | Short bullets: key benefit; natural ingredients; certification
Household & Eco — Lifestyle 40 : Technical 60 | Short bullets: eco benefit; effectiveness; key feature
Supplements & Wellness — Lifestyle 30 : Technical 70 | Short bullets: main benefit; key ingredients; dosage
Frozen — Lifestyle 60 : Technical 40 | Short bullets: convenience; quality; sourcing
Chilled — Lifestyle 70 : Technical 30 | Short bullets: freshness; sourcing; versatility
General — Lifestyle 60 : Technical 40 | Short bullets: what it is; who it's for; core benefit

HTML & CONTENT RULES

A) short_html (for listings/cards)
- Exactly one <p>…</p> containing three bullet fragments separated by <br>.
- Each fragment 2–8 words; sentence case; no trailing full stops.
- Structure: Line 1 = sourcing/origin hook; Line 2 = key benefit; Line 3 = versatility or dietary info.
- Example: <p>Organic chickpeas from small UK producers<br>Rich in plant protein and fibre<br>Versatile store cupboard staple</p>

B) long_html (product page, ordered <p> blocks)
1) Meta description paragraph — one sentence, 150–160 characters; SEO-optimized; include product name; approachable, benefit-led; no retail terms; no em dashes.

2) Lifestyle paragraph — why you'll love it, who it's for. Warm, inviting tone. Use "you" language. Frame ethical choices as delightful discoveries. This is where the EarthFare personality shines.

3) Technical paragraph — main ingredients, sourcing specifics, certifications. Mention producer or region if known. Be factual but warm. Include any standout craft or heritage story.

4) Spec lines (separate <p> tags) only if data is present:
   • <p>Weight: {weight}.</p>
   • <p>Made in UK.</p> only if origin confirms UK, or <p>Origin: {country}.</p> for non-UK.
   • <p>{Dietary info}.</p> — e.g., "Organic. Gluten Free. Vegan."

C) Normalisation & Safety checks
- Trim whitespace; ensure balanced, ordered <p> tags.
- If length issues arise, shorten lifestyle text first, never the meta.
- Remove duplicate facts and promotional fluff.
- No pricing, shipping, stock, or service language.

QUALITY BAR
- Clear what it is, why you'll love it, and relevant specs.
- Tone: warm, conversational, UK spelling, joyfully sustainable.
- Feel like a recommendation from a knowledgeable friend.
- Celebrate the product without preaching.

CRITICAL: The first paragraph of long_html MUST be the meta description. Keep it punchy and SEO-friendly.
""".strip()


def initialize_client():
    """Initialize OpenAI client with API key"""
    global client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set - brand voice generation will fail")
        return False
    client = AsyncOpenAI(api_key=api_key)
    return True


async def generate(products: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """
    Generate brand voice descriptions for products with retry logic
    Args:
        products: List of normalized product dicts
        category: Product category
    Returns:
        List of products with enhanced descriptions
    """
    # Ensure client is initialized
    if client is None:
        initialize_client()

    enhanced_products = []

    for idx, product in enumerate(products):
        try:
            logger.info(f"Processing product {idx + 1}/{len(products)}: {product.get('name', 'Unknown')}")
            enhanced = await generate_single_product(product, category)
            enhanced_products.append(enhanced)
        except Exception as e:
            logger.error(f"Failed to process {product.get('name', 'Unknown')}: {e}")
            # Return product with error marker
            product["descriptions"] = {
                "shortDescription": "<p>Processing error</p>",
                "metaDescription": "Product description generation failed.",
                "longDescription": "<p>Unable to generate description.</p>"
            }
            product["_generation_error"] = str(e)
            enhanced_products.append(product)

    return enhanced_products


async def generate_single_product(product: Dict[str, Any], category: str) -> Dict[str, Any]:
    """
    Generate description for single product with 3 retries
    Args:
        product: Normalized product dict
        category: Product category
    Returns:
        Product with descriptions added
    Raises:
        Exception: After 3 failed retries
    """
    if client is None:
        raise Exception("OpenAI client not initialized - check OPENAI_API_KEY")

    # Filter specs to only allowed ones for this category
    filtered_specs = filter_specifications(product.get("specifications", {}), category)
    product["specifications"] = filtered_specs

    # Build prompt
    prompt = build_prompt(product, category)

    # Try OpenAI with retries
    last_error = None
    for attempt in range(1, OPENAI_MAX_RETRIES + 1):
        try:
            logger.debug(f"OpenAI attempt {attempt}/{OPENAI_MAX_RETRIES} for {product.get('name')}")

            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=1200,
                timeout=float(OPENAI_TIMEOUT)
            )

            content = response.choices[0].message.content

            if not content:
                raise Exception("OpenAI returned empty response")

            # Parse response
            descriptions = parse_openai_response(content)

            # Sanitize output
            descriptions = sanitize_descriptions(descriptions, product.get("name", ""))

            # Update product
            product["descriptions"] = descriptions
            logger.info(f"Successfully generated descriptions for {product.get('name')}")
            return product

        except OpenAIError as e:
            last_error = e
            logger.warning(f"OpenAI attempt {attempt}/{OPENAI_MAX_RETRIES} failed: {e}")

            if attempt < OPENAI_MAX_RETRIES:
                # Exponential backoff
                wait_time = 2 ** attempt
                logger.info(f"Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                # Final attempt failed
                raise Exception(f"OpenAI failed after {OPENAI_MAX_RETRIES} retries: {last_error}")

        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error in attempt {attempt}: {e}")

            if attempt < OPENAI_MAX_RETRIES:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
            else:
                raise Exception(f"Generation failed after {OPENAI_MAX_RETRIES} retries: {last_error}")

    # Should not reach here, but just in case
    raise Exception(f"Generation failed: {last_error}")


def filter_specifications(specs: Dict[str, Any], category: str) -> Dict[str, Any]:
    """
    Filter specs to only allowed keys for category
    Args:
        specs: Product specifications dict
        category: Product category
    Returns:
        Filtered specifications dict
    """
    # Get allowed specs for this category (with fallback to General)
    allowed = ALLOWED_SPECS.get(category, ALLOWED_SPECS.get("General", set()))

    # Filter to only allowed specs
    filtered = {k: v for k, v in specs.items() if k in allowed}

    logger.debug(f"Filtered specs for {category}: kept {len(filtered)}/{len(specs)} specs")

    return filtered


def build_prompt(product: Dict[str, Any], category: str) -> str:
    """
    Build OpenAI prompt from product data
    Args:
        product: Product dict
        category: Product category
    Returns:
        Formatted prompt string
    """
    # Create clean product data for prompt
    prompt_data = {
        "name": product.get("name", ""),
        "category": category,
    }

    # Add optional fields if present
    optional_fields = [
        "sku", "brand", "range", "collection", "colour", "pattern",
        "style", "finish", "usage", "audience"
    ]

    for field in optional_fields:
        if product.get(field):
            prompt_data[field] = product[field]

    # Add lists if present
    if product.get("features"):
        prompt_data["features"] = product["features"]

    if product.get("benefits"):
        prompt_data["benefits"] = product["benefits"]

    # Add specifications (already filtered)
    if product.get("specifications"):
        prompt_data["specifications"] = product["specifications"]

    # Add special flags
    if product.get("isNonStick"):
        prompt_data["isNonStick"] = True

    # Build prompt
    return f"Product data:\n{json.dumps(prompt_data, indent=2)}"


def parse_openai_response(content: str) -> Dict[str, str]:
    """
    Parse OpenAI JSON response, handling markdown fences
    Args:
        content: Raw OpenAI response content
    Returns:
        Dict with shortDescription, metaDescription, longDescription
    Raises:
        Exception: If parsing fails
    """
    try:
        # Strip markdown code blocks
        content = content.strip()

        # Remove markdown json fences if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # Parse JSON
        data = json.loads(content)

        # Extract descriptions
        short_html = data.get("short_html", "")
        long_html = data.get("long_html", "")

        if not short_html or not long_html:
            raise Exception("Missing short_html or long_html in response")

        # Extract meta description from first paragraph of long_html
        meta = extract_meta_from_long_html(long_html)

        return {
            "shortDescription": short_html,
            "metaDescription": meta,
            "longDescription": long_html
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON: {e}\nContent: {content}")
        raise Exception(f"Invalid JSON from OpenAI: {e}")

    except Exception as e:
        logger.error(f"Failed to parse OpenAI response: {e}")
        raise


def extract_meta_from_long_html(long_html: str) -> str:
    """
    Extract first paragraph as meta description
    Args:
        long_html: Long description HTML
    Returns:
        Meta description string (150-160 chars)
    """
    # Extract first <p> tag content
    match = re.search(r'<p>(.*?)</p>', long_html, re.DOTALL)

    if match:
        meta = match.group(1).strip()

        # Remove any inner HTML tags
        meta = re.sub(r'<[^>]+>', '', meta)

        # Clamp to 160 chars
        if len(meta) > 160:
            # Try to cut at sentence boundary
            if '.' in meta[:160]:
                last_period = meta[:160].rfind('.')
                meta = meta[:last_period + 1]
            else:
                meta = meta[:157] + "..."

        return meta

    # Fallback: extract plain text from start
    plain = re.sub(r'<[^>]+>', '', long_html)
    plain = plain.strip()

    if len(plain) > 160:
        plain = plain[:157] + "..."

    return plain


def sanitize_descriptions(descriptions: Dict[str, str], product_name: str) -> Dict[str, str]:
    """
    Remove forbidden phrases and validate
    Args:
        descriptions: Dict with description fields
        product_name: Product name for logging
    Returns:
        Sanitized descriptions dict
    """
    for key in ["shortDescription", "metaDescription", "longDescription"]:
        if key in descriptions:
            # Strip forbidden phrases
            descriptions[key] = strip_forbidden_phrases(descriptions[key])

            # Sanitize HTML
            descriptions[key] = sanitize_html(descriptions[key])

    # Validate lengths
    if len(descriptions.get("shortDescription", "")) > 150:
        logger.warning(f"Short description too long for {product_name}: {len(descriptions['shortDescription'])} chars")

    if len(descriptions.get("longDescription", "")) > 2000:
        logger.warning(f"Long description too long for {product_name}: {len(descriptions['longDescription'])} chars")

    return descriptions


# Initialize client on module import
initialize_client()
