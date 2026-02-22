"""
Input Sanitization Module for Sturgeon AI Service

Provides utilities to sanitize user inputs and prevent injection attacks.
"""

import re
import html
from typing import Optional


MAX_PATIENT_HISTORY_LENGTH = 10000
MAX_LAB_TEXT_LENGTH = 50000
MAX_CHALLENGE_LENGTH = 5000


def sanitize_text(
    text: str,
    max_length: Optional[int] = None,
    strip_html: bool = True
) -> str:
    """Sanitize text input.
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length (truncates if exceeded)
        strip_html: Whether to strip HTML tags
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    text = text.strip()
    
    if strip_html:
        text = _strip_html_tags(text)
    
    text = html.escape(text)
    
    text = _remove_control_chars(text)
    
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def sanitize_patient_history(text: str) -> str:
    """Sanitize patient history input."""
    return sanitize_text(text, max_length=MAX_PATIENT_HISTORY_LENGTH)


def sanitize_lab_text(text: str) -> str:
    """Sanitize lab report text."""
    return sanitize_text(text, max_length=MAX_LAB_TEXT_LENGTH)


def sanitize_challenge(text: str) -> str:
    """Sanitize user challenge/input."""
    return sanitize_text(text, max_length=MAX_CHALLENGE_LENGTH)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal.
    
    Args:
        filename: Original filename
        
    Returns:
        Safe filename
    """
    if not filename:
        return "unnamed"
    
    filename = os_path_basename(filename)
    
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    filename = re.sub(r'\.{2,}', '.', filename)
    
    filename = re.sub(r'^\.+', '', filename)
    
    if len(filename) > 255:
        name, ext = os_path_splitext(filename)
        filename = name[:250] + ext
    
    return filename or "unnamed"


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    return text


def _remove_control_chars(text: str) -> str:
    """Remove potentially dangerous control characters."""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


def os_path_basename(path: str) -> str:
    """Cross-platform basename."""
    return path.replace("\\", "/").split("/")[-1]


def os_path_splitext(path: str) -> tuple:
    """Cross-platform splitext."""
    parts = path.rsplit(".", 1)
    if len(parts) == 2:
        return parts[0], "." + parts[1]
    return path, ""


def validate_file_type(filename: str, allowed_extensions: set) -> bool:
    """Validate file extension.
    
    Args:
        filename: Filename to check
        allowed_extensions: Set of allowed extensions (e.g., {'.pdf', '.txt'})
        
    Returns:
        True if extension is allowed
    """
    _, ext = os_path_splitext(filename.lower())
    return ext in allowed_extensions


def validate_image_type(content_type: str) -> bool:
    """Validate image content type."""
    allowed = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/bmp",
        "image/gif",
    }
    return content_type.lower() in allowed
