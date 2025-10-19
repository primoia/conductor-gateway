"""
Pydantic models for Screenplay API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScreenplayCreate(BaseModel):
    """Request model for creating a new screenplay."""

    name: str = Field(..., min_length=1, max_length=200, description="Unique screenplay name")
    description: Optional[str] = Field(None, max_length=500, description="Screenplay description")
    tags: list[str] = Field(default_factory=list, description="Tags for search and categorization")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "My First Screenplay",
                "description": "A sample screenplay for testing",
                "tags": ["tutorial", "sample"],
            }
        }
    )


class ScreenplayUpdate(BaseModel):
    """Request model for updating an existing screenplay."""

    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Screenplay name")
    description: Optional[str] = Field(None, max_length=500, description="Screenplay description")
    tags: Optional[list[str]] = Field(None, description="Tags for search and categorization")
    content: Optional[str] = Field(None, description="Markdown content of the screenplay")
    is_deleted: Optional[bool] = Field(None, alias="isDeleted", description="Soft delete flag")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Screenplay Name",
                "description": "Updated description",
                "tags": ["updated", "v2"],
                "content": "# Updated Content\n\nNew screenplay content here.",
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
