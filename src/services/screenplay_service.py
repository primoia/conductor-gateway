"""
Service layer for Screenplay operations.
Handles business logic and MongoDB interactions.
"""

import logging
from datetime import UTC, datetime
from typing import Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from src.utils.file_path_validator import validate_file_path, sanitize_file_path
from src.utils.markdown_validator import validate_markdown_content, validate_markdown_file_extension, sanitize_markdown_content
from src.utils.duplicate_detector import generate_file_key, generate_content_hash, is_same_file_path, is_same_file_content
from src.middleware.validation_middleware import ValidationMiddleware

logger = logging.getLogger(__name__)


class ScreenplayService:
    """Service class for managing screenplays in MongoDB."""

    def __init__(self, db: Database):
        """
        Initialize the service with a MongoDB database.

        Args:
            db: PyMongo database instance
        """
        self.collection = db["screenplays"]
        self.agent_instances = db["agent_instances"]
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for the screenplays collection."""
        try:
            # Ensure 'name' is NOT unique (we allow duplicate names)
            # Drop legacy unique index on name if it exists
            try:
                indexes = self.collection.index_information()
                for idx_name, idx_info in indexes.items():
                    if idx_info.get('key') == [('name', 1)] and idx_info.get('unique'):
                        self.collection.drop_index(idx_name)
                        logger.info("Dropped legacy unique index on screenplays.name")
            except Exception as e:
                logger.warning(f"Could not inspect/drop legacy name index: {e}")
            # Keep a regular index on name for performance (non-unique)
            self.collection.create_index("name")
            logger.info("Ensured non-unique index on screenplays.name")

            # Index for soft delete queries
            self.collection.create_index("isDeleted")
            logger.info("Created index on screenplays.isDeleted")

            # Text index for search functionality
            self.collection.create_index(
                [("name", "text"), ("description", "text"), ("tags", "text")]
            )
            logger.info("Created text index on screenplays for search")

            # Unique partial index on filePath for active (non-deleted) docs
            self.collection.create_index(
                [("filePath", 1)],
                name="uniq_active_filePath",
                unique=True,
                partialFilterExpression={"filePath": {"$exists": True, "$ne": None}, "isDeleted": False},
            )
            logger.info("Ensured unique partial index on screenplays.filePath (active only)")
            
            # Unique partial index on importPath for active (non-deleted) docs
            self.collection.create_index(
                [("importPath", 1)],
                name="uniq_active_importPath",
                unique=True,
                partialFilterExpression={"importPath": {"$exists": True, "$ne": None}, "isDeleted": False},
            )
            # Regular index on exportPath
            self.collection.create_index("exportPath")
            logger.info("Ensured unique index on importPath (active) and index on exportPath")
            
            # Unique partial index on fileKey for active docs
            self.collection.create_index(
                [("fileKey", 1)],
                name="uniq_active_fileKey",
                unique=True,
                partialFilterExpression={"fileKey": {"$exists": True, "$ne": None}, "isDeleted": False},
            )
            logger.info("Ensured unique partial index on screenplays.fileKey (active only)")
            
            # Index for content hash (duplicate detection)
            self.collection.create_index("contentHash")
            logger.info("Created index on screenplays.contentHash")
        except Exception as e:
            logger.warning(f"Index creation warning (may already exist): {e}")

    def create_screenplay(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        working_directory: Optional[str] = None,
        file_path: Optional[str] = None,
        import_path: Optional[str] = None,
        export_path: Optional[str] = None,
        content: Optional[str] = None
    ) -> dict:
        """
        Create a new screenplay with default content.

        Args:
            name: Unique screenplay name
            description: Optional description
            tags: Optional list of tags
            working_directory: Optional default working directory for agents
            file_path: Optional full path to the markdown file on disk
            import_path: Optional path from which the screenplay was imported
            export_path: Optional last path where the screenplay was exported
            content: Optional custom content (defaults to template if not provided)

        Returns:
            Created screenplay document

        Raises:
            ValueError: If screenplay with the same name already exists or invalid file_path
        """
        # Validate name using middleware
        name = ValidationMiddleware.validate_screenplay_name(name)
        
        # Validate description and tags using middleware
        description = ValidationMiddleware.validate_description(description)
        tags = ValidationMiddleware.validate_tags(tags)
        
        # Validate and sanitize file paths using middleware
        file_path, import_path, export_path = ValidationMiddleware.validate_file_paths(
            file_path=file_path,
            import_path=import_path,
            export_path=export_path
        )

        # Validate content if provided
        if content is not None:
            content = ValidationMiddleware.validate_markdown_content(content)
        else:
            content = "# Novo Roteiro\n\nComece a escrever seu roteiro aqui..."

        # Enforce uniqueness by path (prefer import_path; fallback to file_path)
        from src.utils.duplicate_detector import extract_file_name_from_path

        if import_path:
            duplicate = self.check_duplicate_by_path(import_path, extract_file_name_from_path(import_path))
            if duplicate:
                raise ValueError(f"Screenplay for path '{import_path}' already exists")

        if file_path:
            duplicate = self.check_duplicate_by_path(file_path, extract_file_name_from_path(file_path))
            if duplicate:
                raise ValueError(f"Screenplay for path '{file_path}' already exists")

        # Generate file key for duplicate detection (prefer path provided)
        file_key = None
        if file_path:
            file_name = extract_file_name_from_path(file_path)
            file_key = generate_file_key(file_path, file_name)
        elif import_path:
            file_name = extract_file_name_from_path(import_path)
            file_key = generate_file_key(import_path, file_name)

        now = datetime.now(UTC)
        document = {
            "name": name,
            "description": description or "",
            "tags": tags or [],
            "content": content,
            "workingDirectory": working_directory,
            "filePath": file_path,
            "importPath": import_path,
            "exportPath": export_path,
            "fileKey": file_key,
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
        except DuplicateKeyError as e:
            msg = str(e)
            logger.error(f"Duplicate key error on screenplay create: {msg}")
            if "uniq_active_importPath" in msg or "importPath" in msg:
                raise ValueError(f"Screenplay for path '{import_path}' already exists")
            if "uniq_active_filePath" in msg or "filePath" in msg:
                raise ValueError(f"Screenplay for path '{file_path}' already exists")
            if "uniq_active_fileKey" in msg or "fileKey" in msg:
                raise ValueError("A screenplay for this file already exists")
            raise ValueError("Duplicate detected while creating screenplay")

    def validate_markdown_content(self, content: str) -> dict:
        """
        Validate Markdown content.

        Args:
            content: Markdown content to validate

        Returns:
            Dictionary with validation results
        """
        is_valid, errors, warnings = validate_markdown_content(content)
        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings
        }

    def check_duplicate_by_path(self, file_path: str, file_name: str, exclude_id: Optional[str] = None) -> Optional[dict]:
        """
        Check if a screenplay with the same file path already exists.

        Args:
            file_path: File path to check
            file_name: File name to check
            exclude_id: Screenplay ID to exclude from check

        Returns:
            Duplicate screenplay document or None
        """
        file_key = generate_file_key(file_path, file_name)
        
        query = {"fileKey": file_key, "isDeleted": False}
        if exclude_id:
            try:
                obj_id = ObjectId(exclude_id)
                query["_id"] = {"$ne": obj_id}
            except Exception:
                logger.warning(f"Invalid exclude_id format: {exclude_id}")

        duplicate = self.collection.find_one(query)
        if duplicate:
            logger.info(f"Found duplicate screenplay by file key: {file_key}")
        return duplicate

    def check_duplicate_by_content(self, content: str, exclude_id: Optional[str] = None) -> Optional[dict]:
        """
        Check if a screenplay with the same content already exists.

        Args:
            content: Content to check
            exclude_id: Screenplay ID to exclude from check

        Returns:
            Duplicate screenplay document or None
        """
        content_hash = generate_content_hash(content)
        
        query = {"contentHash": content_hash, "isDeleted": False}
        if exclude_id:
            try:
                obj_id = ObjectId(exclude_id)
                query["_id"] = {"$ne": obj_id}
            except Exception:
                logger.warning(f"Invalid exclude_id format: {exclude_id}")

        duplicate = self.collection.find_one(query)
        if duplicate:
            logger.info(f"Found duplicate screenplay by content hash")
        return duplicate

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
        working_directory: Optional[str] = None,
        file_path: Optional[str] = None,
        import_path: Optional[str] = None,
        export_path: Optional[str] = None,
        is_deleted: Optional[bool] = None,
    ) -> Optional[dict]:
        """
        Update a screenplay and increment its version.

        Args:
            screenplay_id: Screenplay ID
            name: Optional new name
            description: Optional new description
            tags: Optional new tags
            content: Optional new content
            working_directory: Optional new working directory
            file_path: Optional new file path
            import_path: Optional new import path
            export_path: Optional new export path
            is_deleted: Optional soft delete flag

        Returns:
            Updated screenplay document or None if not found

        Raises:
            ValueError: If name conflict, invalid ID, or invalid file_path
        """
        try:
            obj_id = ObjectId(screenplay_id)
        except Exception:
            logger.warning(f"Invalid screenplay ID format: {screenplay_id}")
            raise ValueError("Invalid screenplay ID format")

        # Check if screenplay exists (allow updates even if deleted)
        existing = self.collection.find_one({"_id": obj_id})
        if not existing:
            logger.warning(f"Screenplay not found for update: {screenplay_id}")
            return None

        # Build update document
        update_doc = {"$set": {"updatedAt": datetime.now(UTC)}, "$inc": {"version": 1}}

        if name is not None:
            # Validate name using middleware (duplicates allowed)
            name = ValidationMiddleware.validate_screenplay_name(name)
            update_doc["$set"]["name"] = name

        if description is not None:
            description = ValidationMiddleware.validate_description(description)
            update_doc["$set"]["description"] = description

        if tags is not None:
            tags = ValidationMiddleware.validate_tags(tags)
            update_doc["$set"]["tags"] = tags

        if content is not None:
            # Validate and sanitize content using middleware
            content = ValidationMiddleware.validate_markdown_content(content)
            update_doc["$set"]["content"] = content
            # Update content hash for duplicate detection
            update_doc["$set"]["contentHash"] = generate_content_hash(content)

        if working_directory is not None:
            update_doc["$set"]["workingDirectory"] = working_directory

        # Validate and update file paths using middleware
        if file_path is not None or import_path is not None or export_path is not None:
            validated_file_path, validated_import_path, validated_export_path = ValidationMiddleware.validate_file_paths(
                file_path=file_path,
                import_path=import_path,
                export_path=export_path
            )
            
            if validated_file_path is not None:
                # Check duplicate by file path (exclude current doc)
                from src.utils.duplicate_detector import extract_file_name_from_path
                duplicate = self.check_duplicate_by_path(validated_file_path, extract_file_name_from_path(validated_file_path), exclude_id=screenplay_id)
                if duplicate:
                    raise ValueError(f"Screenplay for path '{validated_file_path}' already exists")
                update_doc["$set"]["filePath"] = validated_file_path
                # Update file key for duplicate detection
                file_name = extract_file_name_from_path(validated_file_path)
                update_doc["$set"]["fileKey"] = generate_file_key(validated_file_path, file_name)
            
            if validated_import_path is not None:
                # Check duplicate by import path (exclude current doc)
                from src.utils.duplicate_detector import extract_file_name_from_path
                duplicate = self.check_duplicate_by_path(validated_import_path, extract_file_name_from_path(validated_import_path), exclude_id=screenplay_id)
                if duplicate:
                    raise ValueError(f"Screenplay for path '{validated_import_path}' already exists")
                update_doc["$set"]["importPath"] = validated_import_path
                # Also set fileKey if filePath not provided
                if "filePath" not in update_doc["$set"] and not existing.get("filePath"):
                    file_name = extract_file_name_from_path(validated_import_path)
                    update_doc["$set"]["fileKey"] = generate_file_key(validated_import_path, file_name)
            
            if validated_export_path is not None:
                update_doc["$set"]["exportPath"] = validated_export_path

        if is_deleted is not None:
            update_doc["$set"]["isDeleted"] = is_deleted

        # Perform update
        self.collection.update_one({"_id": obj_id}, update_doc)

        # If marking as deleted, also mark related agent_instances as deleted
        if is_deleted is True:
            instances_result = self.agent_instances.update_many(
                {"screenplay_id": screenplay_id, "isDeleted": {"$ne": True}},
                {"$set": {"isDeleted": True, "updated_at": datetime.now(UTC).isoformat()}},
            )

            if instances_result.modified_count > 0:
                logger.info(
                    f"Marked {instances_result.modified_count} agent_instances as deleted "
                    f"for screenplay: {screenplay_id}"
                )
            else:
                logger.info(f"No agent_instances found for screenplay: {screenplay_id}")

        # Fetch and return updated document
        updated_doc = self.collection.find_one({"_id": obj_id})
        logger.info(f"Updated screenplay: {screenplay_id} (new version: {updated_doc['version']})")

        return updated_doc

    def rename_screenplay(self, screenplay_id: str, new_name: str, update_file_paths: bool = True) -> Optional[dict]:
        """
        Rename a screenplay and optionally update file paths.

        Args:
            screenplay_id: Screenplay ID
            new_name: New name for the screenplay
            update_file_paths: Whether to update file paths with new name

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

        # Check if screenplay exists
        existing = self.collection.find_one({"_id": obj_id, "isDeleted": False})
        if not existing:
            logger.warning(f"Screenplay not found for rename: {screenplay_id}")
            return None

        # Validate new name using middleware (duplicates allowed)
        new_name = ValidationMiddleware.validate_screenplay_name(new_name)

        # Build update document
        update_doc = {
            "$set": {
                "name": new_name,
                "updatedAt": datetime.now(UTC)
            },
            "$inc": {"version": 1}
        }

        # Update file paths if requested
        if update_file_paths:
            current_file_path = existing.get("filePath")
            if current_file_path:
                from src.utils.duplicate_detector import extract_file_name_from_path
                from pathlib import Path
                
                # Extract directory and extension
                path_obj = Path(current_file_path)
                directory = str(path_obj.parent)
                extension = path_obj.suffix
                
                # Create new file path with new name
                new_file_path = f"{directory}/{new_name}{extension}"
                new_file_path = sanitize_file_path(new_file_path)
                
                if new_file_path and validate_file_path(new_file_path):
                    # Ensure no duplicate path (exclude current doc)
                    duplicate = self.check_duplicate_by_path(new_file_path, extract_file_name_from_path(new_file_path), exclude_id=screenplay_id)
                    if duplicate:
                        raise ValueError(f"Screenplay for path '{new_file_path}' already exists")
                    update_doc["$set"]["filePath"] = new_file_path
                    # Update file key
                    file_name = extract_file_name_from_path(new_file_path)
                    update_doc["$set"]["fileKey"] = generate_file_key(new_file_path, file_name)

        # Perform update
        self.collection.update_one({"_id": obj_id}, update_doc)

        # Fetch and return updated document
        updated_doc = self.collection.find_one({"_id": obj_id})
        logger.info(f"Renamed screenplay: {screenplay_id} to '{new_name}' (new version: {updated_doc['version']})")

        return updated_doc

    def update_screenplay_working_directory(self, screenplay_id: str, working_directory: str) -> bool:
        """
        Update the working directory for a screenplay.

        Args:
            screenplay_id: Screenplay ID
            working_directory: Absolute path to the working directory

        Returns:
            True if successful, False if screenplay not found

        Raises:
            ValueError: If invalid ID format
        """
        try:
            obj_id = ObjectId(screenplay_id)
        except Exception:
            logger.warning(f"Invalid screenplay ID format: {screenplay_id}")
            raise ValueError("Invalid screenplay ID format")

        # Check if screenplay exists
        existing = self.collection.find_one({"_id": obj_id, "isDeleted": False})
        if not existing:
            logger.warning(f"Screenplay not found: {screenplay_id}")
            return False

        # Update working directory
        result = self.collection.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "workingDirectory": working_directory,
                    "updatedAt": datetime.now(UTC)
                }
            }
        )

        if result.modified_count > 0:
            logger.info(f"Updated working directory for screenplay {screenplay_id}: {working_directory}")
            return True

        return False

    def delete_screenplay(self, screenplay_id: str) -> bool:
        """
        Soft delete a screenplay (sets isDeleted to True).
        Also marks all related agent_instances as deleted.

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

        # First, check if screenplay exists and is not already deleted
        screenplay = self.collection.find_one({"_id": obj_id, "isDeleted": False})
        if not screenplay:
            logger.warning(f"Screenplay not found for deletion: {screenplay_id}")
            return False

        # Mark screenplay as deleted
        result = self.collection.update_one(
            {"_id": obj_id, "isDeleted": False},
            {"$set": {"isDeleted": True, "updatedAt": datetime.now(UTC)}},
        )

        if result.modified_count > 0:
            logger.info(f"Soft deleted screenplay: {screenplay_id}")

            # Mark all related agent_instances as deleted
            instances_result = self.agent_instances.update_many(
                {"screenplay_id": screenplay_id, "isDeleted": {"$ne": True}},
                {"$set": {"isDeleted": True, "updated_at": datetime.now(UTC).isoformat()}},
            )

            if instances_result.modified_count > 0:
                logger.info(
                    f"Marked {instances_result.modified_count} agent_instances as deleted "
                    f"for screenplay: {screenplay_id}"
                )
            else:
                logger.info(f"No agent_instances found for screenplay: {screenplay_id}")

            return True

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
