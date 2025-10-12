"""
Unit and integration tests for Screenplay API endpoints.
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
            with patch("src.api.app.ConductorClient"):
                app = create_app()
                with TestClient(app) as client:
                    # Inject the mock collection into the screenplay service
                    from src.api.routers.screenplays import _screenplay_service
                    if _screenplay_service:
                        _screenplay_service.collection = collection
                    yield client, collection


class TestCreateScreenplay:
    """Tests for POST /api/screenplays"""

    def test_create_screenplay_success(self, client_with_mock_db):
        """Test successful screenplay creation."""
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
        assert data["name"] == "Test Screenplay"
        assert data["description"] == "A test screenplay"
        assert data["tags"] == ["test", "sample"]
        assert "content" in data
        assert data["isDeleted"] is False
        assert data["version"] == 1

    def test_create_screenplay_duplicate_name(self, client_with_mock_db):
        """Test screenplay creation with duplicate name."""
        client, collection = client_with_mock_db

        # Mock DuplicateKeyError
        from pymongo.errors import DuplicateKeyError
        collection.insert_one.side_effect = DuplicateKeyError("Duplicate key error")

        payload = {"name": "Duplicate Name", "description": "Test"}

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response.json()["detail"]

    def test_create_screenplay_missing_name(self, client_with_mock_db):
        """Test screenplay creation without name."""
        client, _ = client_with_mock_db

        payload = {"description": "Missing name"}

        response = client.post("/api/screenplays", json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestListScreenplays:
    """Tests for GET /api/screenplays"""

    def test_list_screenplays_default(self, client_with_mock_db):
        """Test listing screenplays with default parameters."""
        client, collection = client_with_mock_db

        # Mock database response
        mock_docs = [
            {
                "_id": ObjectId(),
                "name": "Screenplay 1",
                "description": "First screenplay",
                "tags": ["tag1"],
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
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["pages"] == 1
        assert len(data["items"]) == 2
        # Verify content field is NOT included in list
        assert "content" not in data["items"][0]

    def test_list_screenplays_with_search(self, client_with_mock_db):
        """Test listing screenplays with search query."""
        client, collection = client_with_mock_db

        mock_docs = [
            {
                "_id": ObjectId(),
                "name": "Searched Screenplay",
                "description": "Contains search term",
                "tags": ["search"],
                "isDeleted": False,
                "version": 1,
                "createdAt": "2025-01-15T10:00:00",
                "updatedAt": "2025-01-15T10:00:00",
            }
        ]

        collection.count_documents.return_value = 1
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
            mock_docs
        )

        response = client.get("/api/screenplays?search=search")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        # Verify search filter was called
        collection.find.assert_called()
        call_args = collection.find.call_args[0][0]
        assert "$text" in call_args
        assert call_args["$text"]["$search"] == "search"

    def test_list_screenplays_pagination(self, client_with_mock_db):
        """Test screenplay list pagination."""
        client, collection = client_with_mock_db

        collection.count_documents.return_value = 25
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = []

        response = client.get("/api/screenplays?page=2&limit=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 2
        assert data["total"] == 25
        assert data["pages"] == 3  # 25 total / 10 per page = 3 pages

    def test_list_screenplays_filters_deleted_by_default(self, client_with_mock_db):
        """Test that deleted screenplays are filtered by default."""
        client, collection = client_with_mock_db

        collection.count_documents.return_value = 0
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = []

        response = client.get("/api/screenplays")

        assert response.status_code == status.HTTP_200_OK
        # Verify isDeleted filter
        collection.find.assert_called()
        call_args = collection.find.call_args[0][0]
        assert call_args["isDeleted"] is False

    def test_list_screenplays_include_deleted(self, client_with_mock_db):
        """Test including deleted screenplays with parameter."""
        client, collection = client_with_mock_db

        collection.count_documents.return_value = 0
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = []

        response = client.get("/api/screenplays?include_deleted=true")

        assert response.status_code == status.HTTP_200_OK
        # Verify no isDeleted filter
        collection.find.assert_called()
        call_args = collection.find.call_args[0][0]
        assert "isDeleted" not in call_args


class TestGetScreenplay:
    """Tests for GET /api/screenplays/{id}"""

    def test_get_screenplay_success(self, client_with_mock_db):
        """Test successful screenplay retrieval."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        mock_doc = {
            "_id": mock_id,
            "name": "Test Screenplay",
            "description": "Description",
            "tags": ["tag"],
            "content": "# Content here",
            "isDeleted": False,
            "version": 1,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T10:00:00",
        }

        collection.find_one.return_value = mock_doc

        response = client.get(f"/api/screenplays/{str(mock_id)}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(mock_id)
        assert data["name"] == "Test Screenplay"
        assert "content" in data  # Full content included
        assert data["content"] == "# Content here"

    def test_get_screenplay_not_found(self, client_with_mock_db):
        """Test screenplay not found."""
        client, collection = client_with_mock_db

        collection.find_one.return_value = None

        response = client.get(f"/api/screenplays/{str(ObjectId())}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_screenplay_invalid_id(self, client_with_mock_db):
        """Test with invalid ObjectId format."""
        client, collection = client_with_mock_db

        collection.find_one.return_value = None

        response = client.get("/api/screenplays/invalid-id")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateScreenplay:
    """Tests for PUT /api/screenplays/{id}"""

    def test_update_screenplay_success(self, client_with_mock_db):
        """Test successful screenplay update."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        existing_doc = {
            "_id": mock_id,
            "name": "Old Name",
            "description": "Old description",
            "tags": ["old"],
            "content": "# Old content",
            "isDeleted": False,
            "version": 1,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T10:00:00",
        }

        updated_doc = {
            "_id": mock_id,
            "name": "New Name",
            "description": "New description",
            "tags": ["new"],
            "content": "# New content",
            "isDeleted": False,
            "version": 2,
            "createdAt": "2025-01-15T10:00:00",
            "updatedAt": "2025-01-15T11:00:00",
        }

        # Mock find_one to return:
        # 1. existing doc (to verify it exists)
        # 2. None (no name conflict check)
        # 3. updated doc (after update)
        collection.find_one.side_effect = [existing_doc, None, updated_doc]
        collection.update_one.return_value = MagicMock(modified_count=1)

        payload = {
            "name": "New Name",
            "description": "New description",
            "tags": ["new"],
            "content": "# New content",
        }

        response = client.put(f"/api/screenplays/{str(mock_id)}", json=payload)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "New Name"
        assert data["version"] == 2  # Version incremented

    def test_update_screenplay_not_found(self, client_with_mock_db):
        """Test updating non-existent screenplay."""
        client, collection = client_with_mock_db

        collection.find_one.return_value = None

        payload = {"name": "New Name"}

        response = client.put(f"/api/screenplays/{str(ObjectId())}", json=payload)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_screenplay_duplicate_name(self, client_with_mock_db):
        """Test updating with a duplicate name."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        existing_doc = {
            "_id": mock_id,
            "name": "Original Name",
            "isDeleted": False,
        }

        conflict_doc = {
            "_id": ObjectId(),
            "name": "Conflicting Name",
        }

        # First call returns the screenplay to update, second call returns conflict
        collection.find_one.side_effect = [existing_doc, conflict_doc]

        payload = {"name": "Conflicting Name"}

        response = client.put(f"/api/screenplays/{str(mock_id)}", json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT


class TestDeleteScreenplay:
    """Tests for DELETE /api/screenplays/{id}"""

    def test_delete_screenplay_success(self, client_with_mock_db):
        """Test successful soft delete."""
        client, collection = client_with_mock_db

        mock_id = ObjectId()
        collection.update_one.return_value = MagicMock(modified_count=1)

        response = client.delete(f"/api/screenplays/{str(mock_id)}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        # Verify soft delete was called
        collection.update_one.assert_called()
        call_args = collection.update_one.call_args
        assert call_args[0][0]["_id"] == mock_id
        assert call_args[0][1]["$set"]["isDeleted"] is True

    def test_delete_screenplay_not_found(self, client_with_mock_db):
        """Test deleting non-existent screenplay."""
        client, collection = client_with_mock_db

        collection.update_one.return_value = MagicMock(modified_count=0)

        response = client.delete(f"/api/screenplays/{str(ObjectId())}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_screenplay_invalid_id(self, client_with_mock_db):
        """Test deleting with invalid ID."""
        client, collection = client_with_mock_db

        collection.update_one.return_value = MagicMock(modified_count=0)

        response = client.delete("/api/screenplays/invalid-id")

        assert response.status_code == status.HTTP_404_NOT_FOUND
