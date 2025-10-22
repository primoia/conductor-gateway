"""
Pydantic models for Screenplay API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MarkdownValidationRequest(BaseModel):
    """Request model for validating Markdown content."""
    
    content: str = Field(..., description="Markdown content to validate")
    file_path: Optional[str] = Field(None, description="Optional file path for context")


class MarkdownValidationResponse(BaseModel):
    """Response model for Markdown validation."""
    
    is_valid: bool = Field(..., description="Whether the Markdown is valid")
    errors: list[str] = Field(default_factory=list, description="List of validation errors")
    warnings: list[str] = Field(default_factory=list, description="List of validation warnings")


class DuplicateCheckRequest(BaseModel):
    """Request model for checking duplicates."""
    
    file_path: str = Field(..., description="File path to check for duplicates")
    file_name: str = Field(..., description="File name to check for duplicates")
    exclude_id: Optional[str] = Field(None, description="Screenplay ID to exclude from check")


class DuplicateCheckResponse(BaseModel):
    """Response model for duplicate check."""

    is_duplicate: bool = Field(..., description="Whether a duplicate exists")
    duplicate_screenplay: Optional["ScreenplayListItem"] = Field(None, description="Duplicate screenplay if found")
    file_key: str = Field(..., description="Generated file key for the path")


class RenameRequest(BaseModel):
    """Request model for renaming screenplays."""
    
    new_name: str = Field(..., min_length=1, max_length=200, description="New screenplay name")
    update_file_paths: bool = Field(True, description="Whether to update file paths with new name")


class ScreenplayCreate(BaseModel):
    """Request model for creating a new screenplay."""

    name: str = Field(..., min_length=1, max_length=200, description="Unique screenplay name")
    description: Optional[str] = Field(None, max_length=500, description="Screenplay description")
    tags: list[str] = Field(default_factory=list, description="Tags for search and categorization")
    file_path: Optional[str] = Field(None, max_length=500, description="Full path to the markdown file on disk")
    import_path: Optional[str] = Field(None, max_length=500, description="Path from which the screenplay was imported")
    export_path: Optional[str] = Field(None, max_length=500, description="Last path where the screenplay was exported")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "My First Screenplay",
                "description": "A sample screenplay for testing",
                "tags": ["tutorial", "sample"],
                "file_path": "/path/to/screenplay.md",
                "import_path": "/imports/screenplay.md",
                "export_path": "/exports/screenplay.md",
            }
        }
    )


class ScreenplayUpdate(BaseModel):
    """Request model for updating an existing screenplay."""

    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Screenplay name")
    description: Optional[str] = Field(None, max_length=500, description="Screenplay description")
    tags: Optional[list[str]] = Field(None, description="Tags for search and categorization")
    content: Optional[str] = Field(None, description="Markdown content of the screenplay")
    file_path: Optional[str] = Field(None, max_length=500, description="Full path to the markdown file on disk")
    import_path: Optional[str] = Field(None, max_length=500, description="Path from which the screenplay was imported")
    export_path: Optional[str] = Field(None, max_length=500, description="Last path where the screenplay was exported")
    is_deleted: Optional[bool] = Field(None, alias="isDeleted", description="Soft delete flag")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Screenplay Name",
                "description": "Updated description",
                "tags": ["updated", "v2"],
                "content": "# Updated Content\n\nNew screenplay content here.",
                "file_path": "/path/to/updated_screenplay.md",
                "import_path": "/imports/updated_screenplay.md",
                "export_path": "/exports/updated_screenplay.md",
                "isDeleted": False,
            }
        }
    )


class ScreenplayResponse(BaseModel):
    """Response model for a single screenplay (includes full content)."""

    id: str = Field(..., description="Unique screenplay ID (MongoDB _id)")
    name: str = Field(..., description="Screenplay name")
    description: Optional[str] = Field(None, description="Screenplay description")
    tags: list[str] = Field(default_factory=list, description="Tags")
    content: str = Field(..., description="Markdown content")
    file_path: Optional[str] = Field(None, description="Full path to the markdown file on disk")
    import_path: Optional[str] = Field(None, description="Path from which the screenplay was imported")
    export_path: Optional[str] = Field(None, description="Last path where the screenplay was exported")
    file_key: Optional[str] = Field(None, description="Unique key for duplicate detection")
    is_deleted: bool = Field(False, alias="isDeleted", description="Soft delete flag")
    version: int = Field(1, description="Version number")
    created_at: datetime = Field(..., alias="createdAt", description="Creation timestamp")
    updated_at: datetime = Field(..., alias="updatedAt", description="Last update timestamp")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Sample Screenplay",
                "description": "A sample screenplay",
                "tags": ["sample", "tutorial"],
                "content": "# Sample Screenplay\n\nThis is the content.",
                "file_path": "/path/to/sample_screenplay.md",
                "import_path": "/imports/sample_screenplay.md",
                "export_path": "/exports/sample_screenplay.md",
                "file_key": "sample_screenplay_key_123",
                "isDeleted": False,
                "version": 1,
                "createdAt": "2025-01-15T10:30:00Z",
                "updatedAt": "2025-01-15T10:30:00Z",
            }
        }
    )


class ScreenplayListItem(BaseModel):
    """Response model for screenplay list items (no content field for performance)."""

    id: str = Field(..., description="Unique screenplay ID")
    name: str = Field(..., description="Screenplay name")
    description: Optional[str] = Field(None, description="Screenplay description")
    tags: list[str] = Field(default_factory=list, description="Tags")
    file_path: Optional[str] = Field(None, description="Full path to the markdown file on disk")
    import_path: Optional[str] = Field(None, description="Path from which the screenplay was imported")
    export_path: Optional[str] = Field(None, description="Last path where the screenplay was exported")
    file_key: Optional[str] = Field(None, description="Unique key for duplicate detection")
    is_deleted: bool = Field(False, alias="isDeleted", description="Soft delete flag")
    version: int = Field(1, description="Version number")
    created_at: datetime = Field(..., alias="createdAt", description="Creation timestamp")
    updated_at: datetime = Field(..., alias="updatedAt", description="Last update timestamp")

    model_config = ConfigDict(populate_by_name=True)


class ScreenplayListResponse(BaseModel):
    """Response model for paginated screenplay list."""

    items: list[ScreenplayListItem] = Field(..., description="List of screenplays")
    total: int = Field(..., description="Total number of screenplays matching the query")
    page: int = Field(..., description="Current page number")
    pages: int = Field(..., description="Total number of pages")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "Sample Screenplay 1",
                        "description": "First screenplay",
                        "tags": ["sample"],
                        "file_path": "/path/to/sample_screenplay1.md",
                        "isDeleted": False,
                        "version": 1,
                        "createdAt": "2025-01-15T10:30:00Z",
                        "updatedAt": "2025-01-15T10:30:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "pages": 1,
            }
        }
    )
