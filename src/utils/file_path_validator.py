"""
File path validation utilities for screenplay file paths.
Implements security checks to prevent path traversal attacks.
"""

import os
import re
from pathlib import Path
from typing import Optional


def validate_file_path(file_path: Optional[str]) -> bool:
    """
    Validate if the file path is safe and secure.
    
    Args:
        file_path: The file path to validate (can be None)
        
    Returns:
        True if the path is valid and safe, False otherwise
    """
    if file_path is None:
        return True  # None is allowed (optional field)
    
    if not isinstance(file_path, str):
        return False
    
    # Check for empty string
    if not file_path.strip():
        return False
    
    # Check for path traversal attempts
    if '..' in file_path or file_path.startswith('/'):
        return False
    
    # Check for dangerous characters
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\x00']
    if any(char in file_path for char in dangerous_chars):
        return False
    
    # Check for allowed file extensions
    allowed_extensions = ['.md', '.txt', '.markdown']
    if not any(file_path.lower().endswith(ext) for ext in allowed_extensions):
        return False
    
    # Check for reasonable path length
    if len(file_path) > 500:
        return False
    
    # Check for valid path structure (no double slashes, etc.)
    if '//' in file_path or file_path.startswith('\\'):
        return False
    
    return True


def sanitize_file_path(file_path: Optional[str]) -> Optional[str]:
    """
    Sanitize a file path by removing dangerous characters and normalizing.
    
    Args:
        file_path: The file path to sanitize
        
    Returns:
        Sanitized file path or None if invalid
    """
    if file_path is None:
        return None
    
    if not isinstance(file_path, str):
        return None
    
    # Remove leading/trailing whitespace
    file_path = file_path.strip()
    
    if not file_path:
        return None
    
    # Replace backslashes with forward slashes
    file_path = file_path.replace('\\', '/')
    
    # Remove double slashes
    while '//' in file_path:
        file_path = file_path.replace('//', '/')
    
    # Remove leading slash if present
    if file_path.startswith('/'):
        file_path = file_path[1:]
    
    # Check if valid after sanitization
    if validate_file_path(file_path):
        return file_path
    
    return None


def get_safe_filename(file_path: str) -> str:
    """
    Extract a safe filename from a file path.
    
    Args:
        file_path: The file path to extract filename from
        
    Returns:
        Safe filename or empty string if invalid
    """
    if not validate_file_path(file_path):
        return ""
    
    try:
        path = Path(file_path)
        return path.name
    except Exception:
        return ""


def is_relative_path(file_path: str) -> bool:
    """
    Check if the file path is a relative path (not absolute).
    
    Args:
        file_path: The file path to check
        
    Returns:
        True if the path is relative, False otherwise
    """
    if not file_path:
        return False
    
    # Check if it starts with drive letter (Windows) or root (Unix)
    if re.match(r'^[A-Za-z]:', file_path) or file_path.startswith('/'):
        return False
    
    return True