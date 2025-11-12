"""
API Router for Screenplay endpoints.
Implements CRUD operations for screenplay management.
"""

import logging

from fastapi import APIRouter, Body, HTTPException, Query, status
from pymongo.database import Database

from src.models.screenplay import (
    ScreenplayCreate,
    ScreenplayListResponse,
    ScreenplayResponse,
    ScreenplayUpdate,
    ScreenplayListItem,
    MarkdownValidationRequest,
    MarkdownValidationResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    RenameRequest,
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
            name=data.name,
            description=data.description,
            tags=data.tags,
            working_directory=data.working_directory,
            file_path=data.file_path,
            import_path=data.import_path,
            export_path=data.export_path
        )

        # Convert MongoDB document to response model
        return ScreenplayResponse(
            id=str(document["_id"]),
            name=document["name"],
            description=document.get("description", ""),
            tags=document.get("tags", []),
            content=document["content"],
            working_directory=document.get("workingDirectory"),
            file_path=document.get("filePath"),
            import_path=document.get("importPath"),
            export_path=document.get("exportPath"),
            file_key=document.get("fileKey"),
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
                working_directory=doc.get("workingDirectory"),
                file_path=doc.get("filePath"),
                import_path=doc.get("importPath"),
                export_path=doc.get("exportPath"),
                file_key=doc.get("fileKey"),
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
            working_directory=document.get("workingDirectory"),
            file_path=document.get("filePath"),
            import_path=document.get("importPath"),
            export_path=document.get("exportPath"),
            file_key=document.get("fileKey"),
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
            working_directory=data.working_directory,
            file_path=data.file_path,
            import_path=data.import_path,
            export_path=data.export_path,
            is_deleted=data.is_deleted,
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
            working_directory=document.get("workingDirectory"),
            file_path=document.get("filePath"),
            import_path=document.get("importPath"),
            export_path=document.get("exportPath"),
            file_key=document.get("fileKey"),
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


@router.post("/validate-markdown", response_model=MarkdownValidationResponse)
async def validate_markdown(data: MarkdownValidationRequest):
    """
    Validate Markdown content.

    Args:
        data: Markdown validation request

    Returns:
        Validation results with errors and warnings

    Raises:
        HTTPException: If service unavailable
    """
    service = get_service()

    try:
        result = service.validate_markdown_content(data.content)
        return MarkdownValidationResponse(
            is_valid=result["is_valid"],
            errors=result["errors"],
            warnings=result["warnings"]
        )

    except Exception as e:
        logger.error(f"Error validating Markdown: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate(data: DuplicateCheckRequest):
    """
    Check for duplicate screenplays by file path.

    Args:
        data: Duplicate check request

    Returns:
        Duplicate check results

    Raises:
        HTTPException: If service unavailable
    """
    service = get_service()

    try:
        duplicate = service.check_duplicate_by_path(
            file_path=data.file_path,
            file_name=data.file_name,
            exclude_id=data.exclude_id
        )

        if duplicate:
            duplicate_item = ScreenplayListItem(
                id=str(duplicate["_id"]),
                name=duplicate["name"],
                description=duplicate.get("description", ""),
                tags=duplicate.get("tags", []),
                file_path=duplicate.get("filePath"),
                import_path=duplicate.get("importPath"),
                export_path=duplicate.get("exportPath"),
                file_key=duplicate.get("fileKey"),
                isDeleted=duplicate.get("isDeleted", False),
                version=duplicate.get("version", 1),
                createdAt=duplicate["createdAt"],
                updatedAt=duplicate["updatedAt"],
            )
        else:
            duplicate_item = None

        from src.utils.duplicate_detector import generate_file_key
        file_key = generate_file_key(data.file_path, data.file_name)

        return DuplicateCheckResponse(
            is_duplicate=duplicate is not None,
            duplicate_screenplay=duplicate_item,
            file_key=file_key
        )

    except Exception as e:
        logger.error(f"Error checking for duplicates: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{screenplay_id}/rename", response_model=ScreenplayResponse)
async def rename_screenplay(screenplay_id: str, data: RenameRequest):
    """
    Rename a screenplay and optionally update file paths.

    Args:
        screenplay_id: Screenplay ID
        data: Rename request data

    Returns:
        Updated screenplay document

    Raises:
        HTTPException: If screenplay not found, name conflict, or service unavailable
    """
    service = get_service()

    try:
        document = service.rename_screenplay(
            screenplay_id=screenplay_id,
            new_name=data.new_name,
            update_file_paths=data.update_file_paths
        )

        if not document:
            logger.warning(f"Screenplay not found for rename: {screenplay_id}")
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
            working_directory=document.get("workingDirectory"),
            file_path=document.get("filePath"),
            import_path=document.get("importPath"),
            export_path=document.get("exportPath"),
            file_key=document.get("fileKey"),
            isDeleted=document.get("isDeleted", False),
            version=document.get("version", 1),
            createdAt=document["createdAt"],
            updatedAt=document["updatedAt"],
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Screenplay rename validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error renaming screenplay {screenplay_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch("/{screenplay_id}/working-directory")
async def update_screenplay_working_directory(
    screenplay_id: str,
    working_directory: str = Body(..., embed=True, description="Working directory path")
):
    """
    Update the working directory for a screenplay.

    This working directory will be inherited by all new agent instances created from this screenplay.

    Args:
        screenplay_id: Screenplay ID
        working_directory: Absolute path to the working directory

    Returns:
        Success message

    Raises:
        HTTPException: If screenplay not found, invalid path, or service unavailable
    """
    service = get_service()

    # Basic validation
    if not working_directory:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="working_directory is required"
        )

    if not working_directory.startswith('/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="working_directory must be an absolute path (start with /)"
        )

    try:
        result = service.update_screenplay_working_directory(
            screenplay_id=screenplay_id,
            working_directory=working_directory
        )

        if not result:
            logger.warning(f"Screenplay not found for working directory update: {screenplay_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screenplay with id '{screenplay_id}' not found"
            )

        logger.info(f"Updated working directory for screenplay {screenplay_id}: {working_directory}")
        return {
            "message": "Working directory updated successfully",
            "working_directory": working_directory
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating working directory for screenplay {screenplay_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))