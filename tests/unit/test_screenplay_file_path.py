"""
Unit tests for screenplay file_path functionality.
"""

import pytest
from bson import ObjectId
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.api.app import create_app


@pytest.fixture
def mock_mongo_db():
    """Mock MongoDB database."""
    db = MagicMock()
    collection = MagicMock()
    db.__getitem__ = MagicMock(return_value=collection)
    return db, collection


@pytest.fixture
def client_with_mock_db(mock_mongo_db):
    """Test client with mocked MongoDB."""
    db, collection = mock_mongo_db

    # Mock the MongoDB connection in lifespan
    with patch("src.api.app.MongoClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=db)
        mock_client.admin.command = MagicMock(return_value={"ok": 1})
        mock_client_class.return_value = mock_client

        # Mock MCP server startup
        with patch("src.api.app.start_mcp_server"):
            # Mock ConductorClient
            with patch("src.api.app.ConductorClient") as mock_conductor_class:
                mock_conductor = MagicMock()
                mock_conductor.close = MagicMock(return_value=None)
                mock_conductor_class.return_value = mock_conductor
                
                # Mock the global conductor_client variable
                with patch("src.api.app.conductor_client", mock_conductor):
                    app = create_app()
                    with TestClient(app) as client:
                        # Inject the mock collection into the screenplay service
                        from src.api.routers.screenplays import _screenplay_service
                        if _screenplay_service:
                            _screenplay_service.collection = collection
                        yield client, collection


class TestScreenplayFilePath:
    """Tests for screenplay file_path functionality."""

    def test_create_screenplay_with_valid_file_path(self, client_with_mock_db):
        """Test creating screenplay with valid file path."""
        client, collection = client_with_mock_db

        # Mock insert_one response
        mock_id = ObjectId()
        collection.insert_one.return_value = MagicMock(inserted_id=mock_id)

        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": "folder/screenplay.md",
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_path"] == "folder/screenplay.md"

    def test_create_screenplay_with_invalid_file_path(self, client_with_mock_db):
        """Test creating screenplay with invalid file path."""
        client, collection = client_with_mock_db

        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": "../invalid/path.md",  # Path traversal attempt
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Invalid file path" in response.json()["detail"]

    def test_create_screenplay_with_invalid_extension(self, client_with_mock_db):
        """Test creating screenplay with invalid file extension."""
        client, collection = client_with_mock_db

        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": "folder/screenplay.exe",  # Invalid extension
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Invalid file path" in response.json()["detail"]

    def test_create_screenplay_without_file_path(self, client_with_mock_db):
        """Test creating screenplay without file path (should be valid)."""
        client, collection = client_with_mock_db

        # Mock insert_one response
        mock_id = ObjectId()
        collection.insert_one.return_value = MagicMock(inserted_id=mock_id)

        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_path"] is None

    def test_update_screenplay_with_valid_file_path(self, client_with_mock_db):
        """Test updating screenplay with valid file path."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        existing_doc = {
            "_id": mock_id,
            "name": "Old Name",
            "description": "Old description",
            "tags": ["old"],
            "content": "# Old content",
            "filePath": "old/path.md",
            "isDeleted": False,
            "version": 1,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T10:00:00",
        }

        updated_doc = {
            "_id": mock_id,
            "name": "Old Name",
            "description": "Old description",
            "tags": ["old"],
            "content": "# Old content",
            "filePath": "new/path.md",
            "isDeleted": False,
            "version": 2,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T11:00:00",
        }

        # Mock find_one to return existing doc, then updated doc
        collection.find_one.side_effect = [existing_doc, updated_doc]
        collection.update_one.return_value = MagicMock(modified_count=1)

        payload = {
            "file_path": "new/path.md",
        }

        response = client.put(f"/api/screenplays/{str(mock_id)}", json=payload)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_path"] == "new/path.md"

    def test_update_screenplay_with_invalid_file_path(self, client_with_mock_db):
        """Test updating screenplay with invalid file path."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        existing_doc = {
            "_id": mock_id,
            "name": "Old Name",
            "isDeleted": False,
        }

        collection.find_one.return_value = existing_doc

        payload = {
            "file_path": "../invalid/path.md",  # Path traversal attempt
        }

        response = client.put(f"/api/screenplays/{str(mock_id)}", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Invalid file path" in response.json()["detail"]

    def test_get_screenplay_with_file_path(self, client_with_mock_db):
        """Test getting screenplay with file path."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        mock_doc = {
            "_id": mock_id,
            "name": "Test Screenplay",
            "description": "Description",
            "tags": ["tag"],
            "content": "# Content here",
            "filePath": "folder/screenplay.md",
            "isDeleted": False,
            "version": 1,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T10:00:00",
        }

        collection.find_one.return_value = mock_doc

        response = client.get(f"/api/screenplays/{str(mock_id)}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_path"] == "folder/screenplay.md"

    def test_list_screenplays_with_file_path(self, client_with_mock_db):
        """Test listing screenplays with file path."""
        client, collection = client_with_mock_db

        mock_docs = [
            {
                "_id": ObjectId(),
                "name": "Screenplay 1",
                "description": "First screenplay",
                "tags": ["tag1"],
                "filePath": "folder/screenplay1.md",
                "isDeleted": False,
                "version": 1,
                "createdAt": "2025-01-15T10:00:00",
                "updatedAt": "2025-01-15T10:00:00",
            },
            {
                "_id": ObjectId(),
                "name": "Screenplay 2",
                "description": "Second screenplay",
                "tags": ["tag2"],
                "filePath": None,  # No file path
                "isDeleted": False,
                "version": 1,
                "createdAt": "2025-01-15T11:00:00",
                "updatedAt": "2025-01-15T11:00:00",
            },
        ]

        collection.count_documents.return_value = 2
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
            mock_docs
        )

        response = client.get("/api/screenplays")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["file_path"] == "folder/screenplay1.md"
        assert data["items"][1]["file_path"] is None

    def test_file_path_sanitization(self, client_with_mock_db):
        """Test that file paths are sanitized during creation."""
        client, collection = client_with_mock_db

        # Mock insert_one response
        mock_id = ObjectId()
        collection.insert_one.return_value = MagicMock(inserted_id=mock_id)

        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": "  folder\\file.md  ",  # Should be sanitized
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_path"] == "folder/file.md"  # Sanitized

    def test_file_path_validation_edge_cases(self, client_with_mock_db):
        """Test file path validation with edge cases."""
        client, collection = client_with_mock_db

        # Test with empty string file_path
        payload = {
            "name": "Test Screenplay",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": "",
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Invalid file path" in response.json()["detail"]

        # Test with very long file_path
        long_path = "a" * 501 + ".md"
        payload = {
            "name": "Test Screenplay 2",
            "description": "A test screenplay",
            "tags": ["test", "sample"],
            "file_path": long_path,
        }

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Invalid file path" in response.json()["detail"]