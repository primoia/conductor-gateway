"""
Service layer for Screenplay operations.
Handles business logic and MongoDB interactions.
"""

import logging
from datetime import UTC, datetime
from typing import Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


class ScreenplayService:
    """Service class for managing screenplays in MongoDB."""

    def __init__(self, collection: Collection):
        """
        Initialize the service with a MongoDB collection.

        Args:
            collection: PyMongo collection instance for screenplays
        """
        self.collection = collection
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for the screenplays collection."""
        try:
            # Unique index on name (case-sensitive)
            self.collection.create_index("name", unique=True)
            logger.info("Created unique index on screenplays.name")

            # Index for soft delete queries
            self.collection.create_index("isDeleted")
            logger.info("Created index on screenplays.isDeleted")

            # Text index for search functionality
            self.collection.create_index(
                [("name", "text"), ("description", "text"), ("tags", "text")]
            )
            logger.info("Created text index on screenplays for search")
        except Exception as e:
            logger.warning(f"Index creation warning (may already exist): {e}")

    def create_screenplay(
        self, name: str, description: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> dict:
        """
        Create a new screenplay with default content.

        Args:
            name: Unique screenplay name
            description: Optional description
            tags: Optional list of tags

        Returns:
            Created screenplay document

        Raises:
            ValueError: If screenplay with the same name already exists
        """
        now = datetime.now(UTC)
        document = {
            "name": name,
            "description": description or "",
            "tags": tags or [],
            "content": "# Novo Roteiro\n\nComece a escrever seu roteiro aqui...",
            "isDeleted": False,
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        }

        try:
            result = self.collection.insert_one(document)
            document["_id"] = result.inserted_id
            logger.info(f"Created screenplay: {name} (id: {result.inserted_id})")
            return document
        except DuplicateKeyError:
            logger.error(f"Screenplay with name '{name}' already exists")
            raise ValueError(f"Screenplay with name '{name}' already exists")

    def get_screenplay_by_id(self, screenplay_id: str) -> Optional[dict]:
        """
        Get a screenplay by its ID (includes full content).

        Args:
            screenplay_id: Screenplay ID (MongoDB _id as string)

        Returns:
            Screenplay document or None if not found or deleted
        """
        try:
            obj_id = ObjectId(screenplay_id)
        except Exception:
            logger.warning(f"Invalid screenplay ID format: {screenplay_id}")
            return None

        document = self.collection.find_one({"_id": obj_id, "isDeleted": False})
        if document:
            logger.info(f"Retrieved screenplay: {screenplay_id}")
        else:
            logger.warning(f"Screenplay not found or deleted: {screenplay_id}")

        return document

    def list_screenplays(
        self,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        include_deleted: bool = False,
    ) -> dict:
        """
        List screenplays with pagination and optional search.

        Args:
            search: Optional search query (searches name, description, tags)
            page: Page number (1-indexed)
            limit: Results per page
            include_deleted: Whether to include soft-deleted screenplays

        Returns:
            Dictionary with items, total, page, and pages
        """
        # Build query filter
        query_filter = {}

        # Apply soft delete filter
        if not include_deleted:
            query_filter["isDeleted"] = False

        # Apply search filter if provided
        if search:
            query_filter["$text"] = {"$search": search}

        # Calculate pagination
        skip = (page - 1) * limit

        # Get total count
        total = self.collection.count_documents(query_filter)

        # Fetch documents (exclude content field for performance)
        cursor = (
            self.collection.find(query_filter, {"content": 0})
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )

        items = list(cursor)

        # Calculate total pages
        pages = (total + limit - 1) // limit if total > 0 else 1

        logger.info(
            f"Listed screenplays: page={page}, limit={limit}, total={total}, "
            f"search={search}, include_deleted={include_deleted}"
        )

        return {"items": items, "total": total, "page": page, "pages": pages}

    def update_screenplay(
        self,
        screenplay_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        content: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Update a screenplay and increment its version.

        Args:
            screenplay_id: Screenplay ID
            name: Optional new name
            description: Optional new description
            tags: Optional new tags
            content: Optional new content

        Returns:
            Updated screenplay document or None if not found

        Raises:
            ValueError: If name conflict or invalid ID
        """
        try:
            obj_id = ObjectId(screenplay_id)
        except Exception:
            logger.warning(f"Invalid screenplay ID format: {screenplay_id}")
            raise ValueError("Invalid screenplay ID format")

        # Check if screenplay exists and is not deleted
        existing = self.collection.find_one({"_id": obj_id, "isDeleted": False})
        if not existing:
            logger.warning(f"Screenplay not found for update: {screenplay_id}")
            return None

        # Build update document
        update_doc = {"$set": {"updatedAt": datetime.now(UTC)}, "$inc": {"version": 1}}

        if name is not None:
            # Check for name conflicts
            if name != existing.get("name"):
                conflict = self.collection.find_one({"name": name})
                if conflict:
                    logger.error(f"Name conflict during update: {name}")
                    raise ValueError(f"Screenplay with name '{name}' already exists")
            update_doc["$set"]["name"] = name

        if description is not None:
            update_doc["$set"]["description"] = description

        if tags is not None:
            update_doc["$set"]["tags"] = tags

        if content is not None:
            update_doc["$set"]["content"] = content

        # Perform update
        self.collection.update_one({"_id": obj_id}, update_doc)

        # Fetch and return updated document
        updated_doc = self.collection.find_one({"_id": obj_id})
        logger.info(f"Updated screenplay: {screenplay_id} (new version: {updated_doc['version']})")

        return updated_doc

    def delete_screenplay(self, screenplay_id: str) -> bool:
        """
        Soft delete a screenplay (sets isDeleted to True).

        Args:
            screenplay_id: Screenplay ID

        Returns:
            True if deleted, False if not found
        """
        try:
            obj_id = ObjectId(screenplay_id)
        except Exception:
            logger.warning(f"Invalid screenplay ID format: {screenplay_id}")
            return False

        result = self.collection.update_one(
            {"_id": obj_id, "isDeleted": False},
            {"$set": {"isDeleted": True, "updatedAt": datetime.now(UTC)}},
        )

        if result.modified_count > 0:
            logger.info(f"Soft deleted screenplay: {screenplay_id}")
            return True

        logger.warning(f"Screenplay not found for deletion: {screenplay_id}")
        return False

    def _document_to_dict(self, document: dict) -> dict:
        """
        Convert MongoDB document to JSON-serializable dict.

        Args:
            document: MongoDB document

        Returns:
            JSON-serializable dictionary with _id converted to string
        """
        if document and "_id" in document:
            document["_id"] = str(document["_id"])
        return document
