"""
Google Lighthouse SEO Validation
Checks meta description length and keyword presence
Auto-fixes meta descriptions that are too short or too long
"""
import logging
import re
from typing import Dict, List, Any
from ..config import SEO_META_MIN_LENGTH, SEO_META_MAX_LENGTH, BANNED_SEO_KEYWORDS

logger = logging.getLogger(__name__)


async def validate_and_fix_meta(
    meta_description: str,
    product_name: str,
    keywords: List[str]
) -> Dict[str, Any]:
    """
    Validate meta description with Lighthouse principles
    Auto-fix if needed
    Args:
        meta_description: Meta description to validate
        product_name: Product name for context
        keywords: List of keywords to check/inject
    Returns:
        Dict with: {
            "original": str,
            "fixed": str,
            "issues": List[str],
            "keywords_present": List[str]
        }
    """
    issues = []
    fixed_meta = meta_description.strip()

    # Check length (150-160 chars ideal)
    original_length = len(fixed_meta)

    if original_length < SEO_META_MIN_LENGTH:
        issues.append("meta_too_short")
        logger.info(f"Meta too short ({original_length} chars), padding with keywords")
        fixed_meta = pad_meta_with_keywords(fixed_meta, keywords, SEO_META_MIN_LENGTH)

    elif original_length > SEO_META_MAX_LENGTH:
        issues.append("meta_too_long")
        logger.info(f"Meta too long ({original_length} chars), truncating")
        fixed_meta = truncate_meta_smartly(fixed_meta, SEO_META_MAX_LENGTH)

    # Filter out banned keywords
    valid_keywords = [kw for kw in keywords if kw.lower() not in BANNED_SEO_KEYWORDS]

    # Check keyword presence
    keywords_present = []
    meta_lower = fixed_meta.lower()

    for kw in valid_keywords:
        if kw.lower() in meta_lower:
            keywords_present.append(kw)

    # If no keywords present and we have valid keywords, try to inject one
    if len(keywords_present) == 0 and valid_keywords:
        issues.append("no_keywords")
        logger.info(f"No keywords present, attempting to inject: {valid_keywords[0]}")
        fixed_meta = inject_keyword(fixed_meta, valid_keywords[0], SEO_META_MAX_LENGTH)

        # Check if injection succeeded
        if valid_keywords[0].lower() in fixed_meta.lower():
            keywords_present.append(valid_keywords[0])

    # Ensure single sentence with period
    fixed_meta = ensure_single_sentence(fixed_meta)

    logger.info(
        f"SEO validation for {product_name}: "
        f"{len(issues)} issues, {len(keywords_present)} keywords present"
    )

    return {
        "original": meta_description,
        "fixed": fixed_meta,
        "issues": issues,
        "keywords_present": keywords_present
    }


def extract_keywords_from_product(product: Dict[str, Any]) -> List[str]:
    """
    Extract keywords from product data for SEO
    Args:
        product: Product dictionary
    Returns:
        List of relevant keywords
    """
    keywords = []

    # Add category
    if category := product.get("category"):
        keywords.append(category)

    # Add brand
    if brand := product.get("brand"):
        keywords.append(brand)

    # Add material from specs
    specs = product.get("specifications", {})
    if material := specs.get("material"):
        keywords.append(material)

    # Add range/collection
    if range_name := product.get("range"):
        keywords.append(range_name)

    # Extract keywords from features
    features = product.get("features", [])
    for feature in features[:3]:  # Max 3 features
        # Extract meaningful words (skip common words)
        words = re.findall(r'\b[A-Z][a-z]+\b', feature)
        keywords.extend(words[:2])  # Max 2 words per feature

    # Deduplicate and filter
    seen = set()
    unique_keywords = []

    for kw in keywords:
        kw_lower = kw.lower()

        # Skip banned keywords
        if kw_lower in BANNED_SEO_KEYWORDS:
            continue

        # Skip duplicates
        if kw_lower in seen:
            continue

        seen.add(kw_lower)
        unique_keywords.append(kw)

    # Limit to top 5 keywords
    return unique_keywords[:5]


def pad_meta_with_keywords(meta: str, keywords: List[str], target_len: int) -> str:
    """
    Add keywords to reach target length
    Args:
        meta: Meta description to pad
        keywords: Keywords to add
        target_len: Target length
    Returns:
        Padded meta description
    """
    if not keywords:
        return meta

    result = meta.rstrip(".")

    # Try adding keywords until we reach target length
    for kw in keywords[:3]:  # Max 3 keywords
        # Skip if keyword already present
        if kw.lower() in result.lower():
            continue

        # Try adding with "with" connector
        test = f"{result} with {kw}"
        if len(test) + 1 <= target_len:  # +1 for period
            result = test
        else:
            break

    # Ensure ends with period
    if not result.endswith("."):
        result += "."

    return result


def truncate_meta_smartly(meta: str, max_len: int) -> str:
    """
    Truncate at sentence boundary if possible
    Args:
        meta: Meta description to truncate
        max_len: Maximum length
    Returns:
        Truncated meta description
    """
    if len(meta) <= max_len:
        return meta

    # Try to end at last period before max_len
    truncated = meta[:max_len]
    last_period = truncated.rfind(".")

    # If period is in last 25% of the truncated text, use it
    if last_period > max_len * 0.75:
        return meta[:last_period + 1]

    # Try to end at last space before max_len
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.85:
        return meta[:last_space].rstrip() + "..."

    # Otherwise hard truncate with ellipsis
    return meta[:max_len - 3] + "..."


def inject_keyword(meta: str, keyword: str, max_len: int) -> str:
    """
    Inject keyword into meta if space permits
    Args:
        meta: Meta description
        keyword: Keyword to inject
        max_len: Maximum allowed length
    Returns:
        Meta with keyword injected (if possible)
    """
    # Skip if keyword already present
    if keyword.lower() in meta.lower():
        return meta

    base = meta.rstrip(".")

    # Try adding with "with" connector
    candidate = f"{base} with {keyword}."

    if len(candidate) <= max_len:
        return candidate

    # Try adding with "for" connector
    candidate = f"{base} for {keyword}."

    if len(candidate) <= max_len:
        return candidate

    # Can't fit keyword, return original
    return meta


def ensure_single_sentence(meta: str) -> str:
    """
    Ensure meta is a single sentence ending with period
    Args:
        meta: Meta description
    Returns:
        Single sentence meta description
    """
    meta = meta.strip()

    # If multiple sentences, keep only first
    sentences = meta.split(". ")
    if len(sentences) > 1:
        meta = sentences[0]

    # Remove line breaks
    meta = meta.replace("\n", " ").replace("\r", "")

    # Collapse multiple spaces
    meta = re.sub(r'\s+', ' ', meta)

    # Ensure ends with period
    if not meta.endswith("."):
        # Check if ends with other punctuation
        if meta.endswith(("!", "?")):
            # Keep as is
            pass
        else:
            meta += "."

    return meta


def validate_keywords(keywords: List[str]) -> List[str]:
    """
    Validate and filter keywords
    Args:
        keywords: List of keywords
    Returns:
        Filtered list of valid keywords
    """
    valid = []

    for kw in keywords:
        kw = kw.strip()

        # Skip empty
        if not kw:
            continue

        # Skip banned keywords
        if kw.lower() in BANNED_SEO_KEYWORDS:
            logger.debug(f"Skipping banned keyword: {kw}")
            continue

        # Skip very short keywords
        if len(kw) < 3:
            continue

        # Skip very long keywords
        if len(kw) > 30:
            continue

        valid.append(kw)

    return valid
