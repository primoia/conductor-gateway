"""
Markdown validation utilities for screenplay content.
Implements validation for Markdown syntax and structure.
"""

import re
from typing import List, Tuple


def validate_markdown_content(content: str) -> Tuple[bool, List[str], List[str]]:
    """
    Validate Markdown content for common issues.
    
    Args:
        content: The Markdown content to validate
        
    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    if not content or not content.strip():
        errors.append("Content cannot be empty")
        return False, errors, warnings
    
    # Check for basic Markdown structure
    lines = content.split('\n')
    
    # Check for proper heading structure
    heading_levels = []
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            if level > 6:
                errors.append(f"Line {i}: Heading level cannot exceed 6 (#{'#' * level})")
            heading_levels.append(level)
    
    # Check for heading hierarchy (warnings only)
    if heading_levels:
        prev_level = 0
        for i, level in enumerate(heading_levels):
            if level > prev_level + 1:
                warnings.append(f"Heading level jumps from H{prev_level} to H{level} (consider using H{prev_level + 1})")
            prev_level = level
    
    # Check for unclosed code blocks
    code_block_open = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('```'):
            code_block_open = not code_block_open
    
    if code_block_open:
        errors.append("Unclosed code block detected")
    
    # Check for unclosed links
    link_pattern = r'\[([^\]]*)\]\(([^)]*)\)'
    for i, line in enumerate(lines, 1):
        if '[' in line and ']' in line and '(' in line and ')' in line:
            # Basic link validation
            if not re.search(link_pattern, line):
                warnings.append(f"Line {i}: Malformed link syntax")
    
    # Check for empty links
    for i, line in enumerate(lines, 1):
        if re.search(r'\[\]\([^)]*\)', line):
            warnings.append(f"Line {i}: Empty link text")
        if re.search(r'\[[^\]]*\]\(\)', line):
            warnings.append(f"Line {i}: Empty link URL")
    
    # Check for very long lines (warnings)
    for i, line in enumerate(lines, 1):
        if len(line) > 120:
            warnings.append(f"Line {i}: Very long line ({len(line)} characters), consider breaking it")
    
    # Check for trailing whitespace
    for i, line in enumerate(lines, 1):
        if line.endswith(' ') or line.endswith('\t'):
            warnings.append(f"Line {i}: Trailing whitespace detected")
    
    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def validate_markdown_file_extension(file_path: str) -> bool:
    """
    Validate that the file has a .md extension.
    
    Args:
        file_path: The file path to validate
        
    Returns:
        True if the file has a .md extension
    """
    if not file_path:
        return False
    
    return file_path.lower().endswith(('.md', '.markdown'))


def sanitize_markdown_content(content: str) -> str:
    """
    Sanitize Markdown content by removing dangerous elements.
    
    Args:
        content: The Markdown content to sanitize
        
    Returns:
        Sanitized Markdown content
    """
    if not content:
        return ""
    
    # Remove potential script tags
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove potential iframe tags
    content = re.sub(r'<iframe[^>]*>.*?</iframe>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove potential object/embed tags
    content = re.sub(r'<(object|embed)[^>]*>.*?</\1>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove null bytes
    content = content.replace('\x00', '')
    
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    return content