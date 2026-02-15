"""
Database MCP Server.

This MCP server provides MongoDB operations for storing and querying data.
Uses the Gateway's internal MongoDB connection.

Port: 5008
"""

import logging
import os
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from src.mcps.base import BaseMCPServer
from src.mcps.registry import MCP_REGISTRY

logger = logging.getLogger(__name__)


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None

    result = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, dict):
            result[key] = serialize_doc(value)
        elif isinstance(value, list):
            result[key] = [
                serialize_doc(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class DatabaseMCP(BaseMCPServer):
    """
    MCP Server for MongoDB operations.

    Provides tools for:
    - Inserting documents
    - Finding documents
    - Updating documents
    - Deleting documents
    - Listing collections

    Uses the Gateway's MongoDB connection.
    """

    def __init__(self, port: int | None = None):
        config = MCP_REGISTRY["database"]

        # Initialize MongoDB connection
        mongodb_url = os.getenv(
            "MONGODB_URL",
            "mongodb://localhost:27017/?authSource=admin"
        )
        self.database_name = os.getenv("MONGODB_DATABASE", "conductor_state")

        self.client = MongoClient(mongodb_url)
        self.db = self.client[self.database_name]

        super().__init__(
            name="database",
            port=port or config["port"],
        )

        logger.info(f"DatabaseMCP connected to {self.database_name}")

    def _register_tools(self) -> None:
        """Register MongoDB tools."""

        @self.mcp.tool(
            name="insert_document",
            description="""Insert a document into a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - document: The document to insert (required)

            Returns the inserted document ID.""",
        )
        async def insert_document(
            collection: str,
            document: dict,
        ) -> dict[str, Any]:
            try:
                # Add timestamp if not present
                if "created_at" not in document:
                    document["created_at"] = datetime.utcnow()

                result = self.db[collection].insert_one(document)

                logger.info(f"Inserted document into {collection}: {result.inserted_id}")
                return {
                    "success": True,
                    "inserted_id": str(result.inserted_id),
                    "collection": collection,
                }
            except Exception as e:
                logger.error(f"Failed to insert document: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="find_documents",
            description="""Find documents in a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - query: MongoDB query filter (default: {} for all documents)
            - limit: Maximum number of documents to return (default: 100)
            - skip: Number of documents to skip (default: 0)
            - sort: Sort specification (e.g., {"created_at": -1})

            Returns list of matching documents.""",
        )
        async def find_documents(
            collection: str,
            query: dict | None = None,
            limit: int = 100,
            skip: int = 0,
            sort: dict | None = None,
        ) -> dict[str, Any]:
            try:
                cursor = self.db[collection].find(query or {})

                if sort:
                    # Convert sort dict to list of tuples
                    sort_list = [(k, v) for k, v in sort.items()]
                    cursor = cursor.sort(sort_list)

                cursor = cursor.skip(skip).limit(limit)

                documents = [serialize_doc(doc) for doc in cursor]

                logger.info(f"Found {len(documents)} documents in {collection}")
                return {
                    "success": True,
                    "count": len(documents),
                    "documents": documents,
                    "collection": collection,
                }
            except Exception as e:
                logger.error(f"Failed to find documents: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="find_one_document",
            description="""Find a single document in a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - query: MongoDB query filter (required)

            Returns the matching document or null.""",
        )
        async def find_one_document(
            collection: str,
            query: dict,
        ) -> dict[str, Any]:
            try:
                document = self.db[collection].find_one(query)

                if document:
                    logger.info(f"Found document in {collection}")
                    return {
                        "success": True,
                        "document": serialize_doc(document),
                        "collection": collection,
                    }
                else:
                    return {
                        "success": True,
                        "document": None,
                        "collection": collection,
                        "message": "No document found matching query",
                    }
            except Exception as e:
                logger.error(f"Failed to find document: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="update_document",
            description="""Update a document in a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - query: MongoDB query filter to find document (required)
            - update: Update operations (required)
                      Use $set, $unset, $inc, etc. for partial updates
            - upsert: Create document if not found (default: False)

            Returns update result.""",
        )
        async def update_document(
            collection: str,
            query: dict,
            update: dict,
            upsert: bool = False,
        ) -> dict[str, Any]:
            try:
                # Add updated_at timestamp
                if "$set" in update:
                    update["$set"]["updated_at"] = datetime.utcnow()
                else:
                    update["$set"] = {"updated_at": datetime.utcnow()}

                result = self.db[collection].update_one(
                    query, update, upsert=upsert
                )

                logger.info(f"Updated {result.modified_count} documents in {collection}")
                return {
                    "success": True,
                    "matched_count": result.matched_count,
                    "modified_count": result.modified_count,
                    "upserted_id": str(result.upserted_id) if result.upserted_id else None,
                    "collection": collection,
                }
            except Exception as e:
                logger.error(f"Failed to update document: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="delete_document",
            description="""Delete a document from a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - query: MongoDB query filter to find document (required)

            Returns delete result.""",
        )
        async def delete_document(
            collection: str,
            query: dict,
        ) -> dict[str, Any]:
            try:
                result = self.db[collection].delete_one(query)

                logger.info(f"Deleted {result.deleted_count} documents from {collection}")
                return {
                    "success": True,
                    "deleted_count": result.deleted_count,
                    "collection": collection,
                }
            except Exception as e:
                logger.error(f"Failed to delete document: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="count_documents",
            description="""Count documents in a MongoDB collection.

            Parameters:
            - collection: Name of the collection (required)
            - query: MongoDB query filter (default: {} for all documents)

            Returns document count.""",
        )
        async def count_documents(
            collection: str,
            query: dict | None = None,
        ) -> dict[str, Any]:
            try:
                count = self.db[collection].count_documents(query or {})

                logger.info(f"Counted {count} documents in {collection}")
                return {
                    "success": True,
                    "count": count,
                    "collection": collection,
                }
            except Exception as e:
                logger.error(f"Failed to count documents: {e}")
                return {"success": False, "error": str(e)}

        @self.mcp.tool(
            name="list_collections",
            description="""List all collections in the database.

            Returns list of collection names and document counts.""",
        )
        async def list_collections() -> dict[str, Any]:
            try:
                collections = []
                for name in self.db.list_collection_names():
                    count = self.db[name].estimated_document_count()
                    collections.append({
                        "name": name,
                        "document_count": count,
                    })

                logger.info(f"Listed {len(collections)} collections")
                return {
                    "success": True,
                    "database": self.database_name,
                    "collection_count": len(collections),
                    "collections": collections,
                }
            except Exception as e:
                logger.error(f"Failed to list collections: {e}")
                return {"success": False, "error": str(e)}

        logger.info("Database MCP tools registered")


# Allow running standalone for testing or future container extraction
if __name__ == "__main__":
    server = DatabaseMCP()
    server.run()
