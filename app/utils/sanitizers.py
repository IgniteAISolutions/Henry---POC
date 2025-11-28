"""
HTML sanitization and forbidden phrase removal
Ported from Supabase TypeScript
"""
import re
import html
from typing import List
from ..config import FORBIDDEN_PHRASES


def strip_forbidden_phrases(content: str) -> str:
    """
    Remove forbidden phrases like 'Harts of Stur', 'Since 1919', etc.
    Args:
        content: HTML or text content to sanitize
    Returns:
        Sanitized content with forbidden phrases removed
    """
    if not content:
        return content

    result = content

    # Normalize entities
    result = result.replace("&nbsp;", " ").replace("\u00A0", " ")

    # Remove each forbidden phrase (case-insensitive, handles inline tags)
    for phrase in FORBIDDEN_PHRASES:
        # Build regex that allows spaces, &nbsp;, or tags between words
        words = phrase.split()
        pattern = r"\b" + r"(?:\s|&nbsp;|<[^>]+>)+".join(re.escape(w) for w in words) + r"\b"
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    # Remove common provenance patterns
    # "Imported from [Country]"
    result = re.sub(r'\bimported\s+from\s+\w+\b', '', result, flags=re.IGNORECASE)

    # Collapse multiple spaces
    result = re.sub(r"\s{2,}", " ", result)

    # Clean up orphaned punctuation
    result = re.sub(r'\s+([.,;:])', r'\1', result)
    result = re.sub(r'([.,;:])\s*\1+', r'\1', result)

    return result.strip()


def sanitize_html(content: str) -> str:
    """
    Remove scripts, styles, and dangerous tags
    Args:
        content: HTML content to sanitize
    Returns:
        Sanitized HTML safe for display
    """
    if not content:
        return content

    # Remove dangerous tags
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<iframe[^>]*>.*?</iframe>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<object[^>]*>.*?</object>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<embed[^>]*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'<link[^>]*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'<meta[^>]*>', '', content, flags=re.IGNORECASE)

    # Remove event handlers
    content = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s+on\w+\s*=\s*\S+', '', content, flags=re.IGNORECASE)

    # Remove javascript: URLs
    content = re.sub(r'javascript:', '', content, flags=re.IGNORECASE)

    return content.strip()


def normalize_paragraphs(content: str, prefer_p_tags: bool = True) -> str:
    """
    Normalize paragraph structure - convert between <p> tags and <br> tags
    Args:
        content: HTML content to normalize
        prefer_p_tags: If True, use <p> tags; if False, use <br> tags
    Returns:
        Normalized HTML
    """
    if not content:
        return content

    # Convert various formats to plain text paragraphs
    # Convert <br><br> to paragraph breaks
    content = re.sub(r'<br\s*/?>\s*<br\s*/?>', '\n\n', content, flags=re.IGNORECASE)

    # Convert </p><p> to paragraph breaks
    content = re.sub(r'</p>\s*<p>', '\n\n', content, flags=re.IGNORECASE)

    # Remove all remaining <p> tags
    content = re.sub(r'</?p[^>]*>', '', content, flags=re.IGNORECASE)

    # Remove single <br> tags (we'll re-add them if needed)
    content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)

    # Split into paragraphs
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

    if prefer_p_tags:
        # Wrap each paragraph in <p> tags
        return ''.join(f'<p>{p}</p>' for p in paragraphs)
    else:
        # Join paragraphs with <br> tags
        return '<br>\n'.join(paragraphs)


def clean_whitespace(content: str) -> str:
    """
    Clean up excessive whitespace while preserving single spaces
    Args:
        content: Text content to clean
    Returns:
        Cleaned content
    """
    if not content:
        return content

    # Replace tabs with spaces
    content = content.replace('\t', ' ')

    # Collapse multiple spaces (except in HTML tags)
    content = re.sub(r'(?<=>)\s+(?=<)', ' ', content)
    content = re.sub(r'(?<![<>])\s{2,}(?![<>])', ' ', content)

    # Remove spaces around tags
    content = re.sub(r'\s+(<[^>]+>)\s+', r'\1', content)

    # Trim
    return content.strip()


def strip_html_tags(content: str) -> str:
    """
    Remove all HTML tags, leaving only text content
    Args:
        content: HTML content
    Returns:
        Plain text content
    """
    if not content:
        return content

    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', '', content)

    # Decode HTML entities
    text = html.unescape(text)

    # Clean whitespace
    text = clean_whitespace(text)

    return text


def enforce_title_in_first_sentence(name: str, sku: str, content: str, prefer_p_tags: bool = True) -> str:
    """
    Replace SKU with product name in first sentence
    Args:
        name: Product name to inject
        sku: SKU to replace
        content: HTML content
        prefer_p_tags: Whether content uses <p> tags or <br> tags
    Returns:
        Content with SKU replaced by name in first sentence
    """
    if not name or not sku or not content:
        return content

    # Build case-insensitive SKU pattern
    sku_pattern = re.compile(rf'\b{re.escape(sku)}\b', re.IGNORECASE)

    if prefer_p_tags:
        # Extract first <p> tag
        match = re.search(r'<p>(.*?)</p>', content, re.DOTALL)
        if match:
            first_p = match.group(1)
            if sku_pattern.search(first_p):
                fixed_p = sku_pattern.sub(name, first_p, count=1)
                return content.replace(match.group(0), f'<p>{fixed_p}</p>', 1)
    else:
        # Extract first line before <br>
        parts = content.split('<br>', 1)
        if len(parts) > 0 and sku_pattern.search(parts[0]):
            parts[0] = sku_pattern.sub(name, parts[0], count=1)
            return '<br>'.join(parts)

    return content


def validate_html_structure(content: str) -> bool:
    """
    Validate that HTML has balanced tags
    Args:
        content: HTML content to validate
    Returns:
        True if HTML structure is valid
    """
    if not content:
        return True

    # Check for balanced <p> tags
    opening_p = len(re.findall(r'<p[^>]*>', content, re.IGNORECASE))
    closing_p = len(re.findall(r'</p>', content, re.IGNORECASE))

    return opening_p == closing_p
