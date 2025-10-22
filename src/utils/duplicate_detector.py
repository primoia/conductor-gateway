"""
Duplicate detection utilities for screenplay file paths.
Implements algorithms for detecting duplicate files based on path and content.
"""

import base64
import hashlib
from typing import Optional

from src.utils.file_path_validator import validate_file_path, sanitize_file_path


def generate_file_key(file_path: str, file_name: str) -> str:
    """
    Generate a unique key for file duplicate detection.
    
    Args:
        file_path: The file path
        file_name: The file name
        
    Returns:
        Base64-encoded unique key
    """
    # Sanitize inputs
    safe_path = sanitize_file_path(file_path) or ""
    safe_name = file_name.strip()
    
    # Create key data
    key_data = f"{safe_path}:{safe_name}"
    
    # Generate hash for consistency
    hash_obj = hashlib.sha256(key_data.encode('utf-8'))
    hash_bytes = hash_obj.digest()
    
    # Encode as base64 and make URL-safe
    key = base64.urlsafe_b64encode(hash_bytes).decode('ascii')
    
    return key


def generate_content_hash(content: str) -> str:
    """
    Generate a hash for content comparison.
    
    Args:
        content: The content to hash
        
    Returns:
        SHA-256 hash of the content
    """
    # Normalize content (remove extra whitespace, normalize line endings)
    normalized_content = content.strip().replace('\r\n', '\n').replace('\r', '\n')
    
    # Generate hash
    hash_obj = hashlib.sha256(normalized_content.encode('utf-8'))
    return hash_obj.hexdigest()


def extract_file_name_from_path(file_path: str) -> str:
    """
    Extract file name from a file path.
    
    Args:
        file_path: The file path
        
    Returns:
        The file name without extension
    """
    if not file_path:
        return ""
    
    # Remove path separators and get the last part
    file_name = file_path.replace('\\', '/').split('/')[-1]
    
    # Remove extension
    if '.' in file_name:
        file_name = file_name.rsplit('.', 1)[0]
    
    return file_name


def is_same_file_path(path1: str, path2: str) -> bool:
    """
    Check if two file paths refer to the same file.
    
    Args:
        path1: First file path
        path2: Second file path
        
    Returns:
        True if the paths refer to the same file
    """
    if not path1 or not path2:
        return False
    
    # Sanitize both paths
    safe_path1 = sanitize_file_path(path1)
    safe_path2 = sanitize_file_path(path2)
    
    if not safe_path1 or not safe_path2:
        return False
    
    # Normalize paths (case-insensitive comparison)
    return safe_path1.lower() == safe_path2.lower()


def is_same_file_content(content1: str, content2: str) -> bool:
    """
    Check if two content strings are the same.
    
    Args:
        content1: First content string
        content2: Second content string
        
    Returns:
        True if the contents are identical
    """
    if not content1 or not content2:
        return content1 == content2
    
    # Generate hashes for comparison
    hash1 = generate_content_hash(content1)
    hash2 = generate_content_hash(content2)
    
    return hash1 == hash2


def calculate_similarity_score(content1: str, content2: str) -> float:
    """
    Calculate similarity score between two content strings.
    
    Args:
        content1: First content string
        content2: Second content string
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not content1 or not content2:
        return 0.0
    
    # Normalize content
    norm1 = content1.strip().replace('\r\n', '\n').replace('\r', '\n')
    norm2 = content2.strip().replace('\r\n', '\n').replace('\r', '\n')
    
    if norm1 == norm2:
        return 1.0
    
    # Simple character-based similarity
    len1, len2 = len(norm1), len(norm2)
    if len1 == 0 or len2 == 0:
        return 0.0
    
    # Calculate Jaccard similarity
    set1 = set(norm1)
    set2 = set(norm2)
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    if union == 0:
        return 0.0
    
    return intersection / union