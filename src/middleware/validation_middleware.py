"""
Validation middleware for screenplay API endpoints.
Provides centralized validation for file paths, Markdown content, and other data.
"""

import logging
from typing import Optional, Tuple, List
from fastapi import HTTPException, status

from src.utils.file_path_validator import validate_file_path, sanitize_file_path
from src.utils.markdown_validator import validate_markdown_content, validate_markdown_file_extension
from src.utils.duplicate_detector import generate_file_key, generate_content_hash

logger = logging.getLogger(__name__)


class ValidationMiddleware:
    """Centralized validation middleware for screenplay operations."""

    @staticmethod
    def validate_file_paths(
        file_path: Optional[str] = None,
        import_path: Optional[str] = None,
        export_path: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Validate and sanitize file paths.
        
        Args:
            file_path: Main file path
            import_path: Import path
            export_path: Export path
            
        Returns:
            Tuple of sanitized paths (file_path, import_path, export_path)
            
        Raises:
            HTTPException: If any path is invalid
        """
        errors = []
        
        # Validate file_path
        if file_path is not None:
            sanitized_file_path = sanitize_file_path(file_path)
            if not sanitized_file_path or not validate_file_path(sanitized_file_path):
                errors.append(f"Invalid file_path: {file_path}")
            else:
                file_path = sanitized_file_path
                
            # Validate file extension
            if not validate_markdown_file_extension(file_path):
                errors.append(f"File must have .md or .markdown extension: {file_path}")
        
        # Validate import_path
        if import_path is not None:
            sanitized_import_path = sanitize_file_path(import_path)
            if not sanitized_import_path or not validate_file_path(sanitized_import_path):
                errors.append(f"Invalid import_path: {import_path}")
            else:
                import_path = sanitized_import_path
                
            # Validate file extension
            if not validate_markdown_file_extension(import_path):
                errors.append(f"Import file must have .md or .markdown extension: {import_path}")
        
        # Validate export_path
        if export_path is not None:
            sanitized_export_path = sanitize_file_path(export_path)
            if not sanitized_export_path or not validate_file_path(sanitized_export_path):
                errors.append(f"Invalid export_path: {export_path}")
            else:
                export_path = sanitized_export_path
                
            # Validate file extension
            if not validate_markdown_file_extension(export_path):
                errors.append(f"Export file must have .md or .markdown extension: {export_path}")
        
        if errors:
            error_message = "; ".join(errors)
            logger.error(f"File path validation failed: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File path validation failed: {error_message}"
            )
        
        return file_path, import_path, export_path

    @staticmethod
    def validate_markdown_content(content: str) -> str:
        """
        Validate and sanitize Markdown content.
        
        Args:
            content: Markdown content to validate
            
        Returns:
            Sanitized Markdown content
            
        Raises:
            HTTPException: If content is invalid
        """
        if not content or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content cannot be empty"
            )
        
        # Validate Markdown content
        is_valid, errors, warnings = validate_markdown_content(content)
        
        if not is_valid:
            error_message = "; ".join(errors)
            logger.error(f"Markdown validation failed: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Markdown validation failed: {error_message}"
            )
        
        if warnings:
            logger.warning(f"Markdown validation warnings: {warnings}")
        
        return content

    @staticmethod
    def validate_screenplay_name(name: str) -> str:
        """
        Validate screenplay name.
        
        Args:
            name: Screenplay name to validate
            
        Returns:
            Validated name
            
        Raises:
            HTTPException: If name is invalid
        """
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Screenplay name cannot be empty"
            )
        
        name = name.strip()
        
        if len(name) > 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Screenplay name cannot exceed 200 characters"
            )
        
        if len(name) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Screenplay name must be at least 1 character"
            )
        
        # Check for dangerous characters
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\x00']
        for char in dangerous_chars:
            if char in name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Screenplay name contains invalid character: {char}"
                )
        
        return name

    @staticmethod
    def validate_description(description: Optional[str]) -> Optional[str]:
        """
        Validate screenplay description.
        
        Args:
            description: Description to validate
            
        Returns:
            Validated description
            
        Raises:
            HTTPException: If description is invalid
        """
        if description is None:
            return None
        
        if len(description) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Description cannot exceed 500 characters"
            )
        
        return description.strip() if description.strip() else None

    @staticmethod
    def validate_tags(tags: Optional[List[str]]) -> List[str]:
        """
        Validate screenplay tags.
        
        Args:
            tags: Tags to validate
            
        Returns:
            Validated tags list
            
        Raises:
            HTTPException: If tags are invalid
        """
        if tags is None:
            return []
        
        if not isinstance(tags, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tags must be a list"
            )
        
        validated_tags = []
        for tag in tags:
            if not isinstance(tag, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All tags must be strings"
                )
            
            tag = tag.strip()
            if not tag:
                continue
                
            if len(tag) > 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tag cannot exceed 50 characters: {tag}"
                )
            
            validated_tags.append(tag)
        
        return validated_tags

    @staticmethod
    def generate_file_key_safe(file_path: str, file_name: str) -> str:
        """
        Generate file key safely with validation.
        
        Args:
            file_path: File path
            file_name: File name
            
        Returns:
            Generated file key
            
        Raises:
            HTTPException: If inputs are invalid
        """
        if not file_path or not file_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File path and file name are required for duplicate detection"
            )
        
        try:
            return generate_file_key(file_path, file_name)
        except Exception as e:
            logger.error(f"Error generating file key: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error generating file key for duplicate detection"
            )

    @staticmethod
    def generate_content_hash_safe(content: str) -> str:
        """
        Generate content hash safely with validation.
        
        Args:
            content: Content to hash
            
        Returns:
            Generated content hash
            
        Raises:
            HTTPException: If content is invalid
        """
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content is required for duplicate detection"
            )
        
        try:
            return generate_content_hash(content)
        except Exception as e:
            logger.error(f"Error generating content hash: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error generating content hash for duplicate detection"
            )