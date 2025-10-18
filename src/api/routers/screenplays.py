"""
API Router for Screenplay endpoints.
Implements CRUD operations for screenplay management.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from pymongo.database import Database

from src.models.screenplay import (
    ScreenplayCreate,
    ScreenplayListResponse,
    ScreenplayResponse,
    ScreenplayUpdate,
    ScreenplayListItem,
)
from src.services.screenplay_service import ScreenplayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screenplays", tags=["Screenplays"])

# Global service instance (will be initialized in app.py lifespan)
_screenplay_service: ScreenplayService | None = None


def init_screenplay_service(db: Database):
    """
    Initialize the screenplay service with MongoDB connection.

    Args:
        db: MongoDB database instance
    """
    global _screenplay_service
    _screenplay_service = ScreenplayService(db)
    logger.info("Initialized ScreenplayService")


def get_service() -> ScreenplayService:
    """
    Get the screenplay service instance.

    Returns:
        ScreenplayService instance

    Raises:
        HTTPException: If service is not initialized
    """
    if _screenplay_service is None:
        logger.error("ScreenplayService not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screenplay service not available",
        )
    return _screenplay_service


@router.post("", response_model=ScreenplayResponse, status_code=status.HTTP_201_CREATED)
async def create_screenplay(data: ScreenplayCreate):
    """
    Create a new screenplay with default content.

    Args:
        data: Screenplay creation data (name, description, tags)

    Returns:
        Created screenplay document

    Raises:
        HTTPException: If name already exists or service unavailable
    """
    service = get_service()

    try:
        document = service.create_screenplay(
            name=data.name, description=data.description, tags=data.tags
        )

        # Convert MongoDB document to response model
        return ScreenplayResponse(
            id=str(document["_id"]),
            name=document["name"],
            description=document.get("description", ""),
            tags=document.get("tags", []),
            content=document["content"],
            isDeleted=document.get("isDeleted", False),
            version=document.get("version", 1),
            createdAt=document["createdAt"],
            updatedAt=document["updatedAt"],
        )

    except ValueError as e:
        logger.error(f"Screenplay creation failed: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating screenplay: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=ScreenplayListResponse)
async def list_screenplays(
    search: str | None = Query(None, description="Search query for name, description, and tags"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    include_deleted: bool = Query(False, description="Include soft-deleted screenplays"),
):
    """
    List screenplays with pagination and optional search.

    Args:
        search: Optional search query
        page: Page number (default: 1)
        limit: Results per page (default: 20, max: 100)
        include_deleted: Whether to include deleted screenplays (default: False)

    Returns:
        Paginated list of screenplays (without content field)

    Raises:
        HTTPException: If service unavailable
    """
    service = get_service()

    try:
        result = service.list_screenplays(
            search=search, page=page, limit=limit, include_deleted=include_deleted
        )

        # Convert documents to response models
        items = [
            ScreenplayListItem(
                id=str(doc["_id"]),
                name=doc["name"],
                description=doc.get("description", ""),
                tags=doc.get("tags", []),
                isDeleted=doc.get("isDeleted", False),
                version=doc.get("version", 1),
                createdAt=doc["createdAt"],
                updatedAt=doc["updatedAt"],
            )
            for doc in result["items"]
        ]

        return ScreenplayListResponse(
            items=items, total=result["total"], page=result["page"], pages=result["pages"]
        )

    except Exception as e:
        logger.error(f"Error listing screenplays: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{screenplay_id}", response_model=ScreenplayResponse)
async def get_screenplay(screenplay_id: str):
    """
    Get a specific screenplay by ID (includes full content).

    Args:
        screenplay_id: Screenplay ID (MongoDB _id)

    Returns:
        Complete screenplay document

    Raises:
        HTTPException: If screenplay not found or service unavailable
    """
    service = get_service()

    try:
        document = service.get_screenplay_by_id(screenplay_id)

        if not document:
            logger.warning(f"Screenplay not found: {screenplay_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screenplay with id '{screenplay_id}' not found",
            )

        return ScreenplayResponse(
            id=str(document["_id"]),
            name=document["name"],
            description=document.get("description", ""),
            tags=document.get("tags", []),
            content=document["content"],
            isDeleted=document.get("isDeleted", False),
            version=document.get("version", 1),
            createdAt=document["createdAt"],
            updatedAt=document["updatedAt"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving screenplay {screenplay_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{screenplay_id}", response_model=ScreenplayResponse)
async def update_screenplay(screenplay_id: str, data: ScreenplayUpdate):
    """
    Update a screenplay and increment its version.

    Args:
        screenplay_id: Screenplay ID
        data: Fields to update (name, description, tags, content)

    Returns:
        Updated screenplay document

    Raises:
        HTTPException: If screenplay not found, name conflict, or service unavailable
    """
    service = get_service()

    try:
        document = service.update_screenplay(
            screenplay_id=screenplay_id,
            name=data.name,
            description=data.description,
            tags=data.tags,
            content=data.content,
        )

        if not document:
            logger.warning(f"Screenplay not found for update: {screenplay_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screenplay with id '{screenplay_id}' not found",
            )

        return ScreenplayResponse(
            id=str(document["_id"]),
            name=document["name"],
            description=document.get("description", ""),
            tags=document.get("tags", []),
            content=document["content"],
            isDeleted=document.get("isDeleted", False),
            version=document.get("version", 1),
            createdAt=document["createdAt"],
            updatedAt=document["updatedAt"],
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Screenplay update validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating screenplay {screenplay_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{screenplay_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screenplay(screenplay_id: str):
    """
    Soft delete a screenplay (sets isDeleted to True).

    Args:
        screenplay_id: Screenplay ID

    Raises:
        HTTPException: If screenplay not found or service unavailable
    """
    service = get_service()

    try:
        success = service.delete_screenplay(screenplay_id)

        if not success:
            logger.warning(f"Screenplay not found for deletion: {screenplay_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screenplay with id '{screenplay_id}' not found",
            )

        logger.info(f"Successfully deleted screenplay: {screenplay_id}")
        return None  # 204 No Content response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting screenplay {screenplay_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
