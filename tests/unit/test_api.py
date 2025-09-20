"""
Tests for API endpoints.
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.api
class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check_get(self, client_without_mcp):
        """Test GET health endpoint."""
        response = client_without_mcp.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "conductor_gateway"
        assert data["version"] == "3.1.0"
        assert "endpoints" in data

    def test_health_check_options(self, client_without_mcp):
        """Test OPTIONS health endpoint."""
        response = client_without_mcp.options("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.api
class TestSynchronousExecuteEndpoint:
    """Test synchronous execute endpoint."""

    @patch('src.utils.mcp_utils.init_agent')
    def test_execute_with_textentries_payload(self, mock_init_agent, client_without_mcp, sample_execution_payload):
        """Test execute endpoint with textEntries payload format."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Agent executed successfully")
        mock_init_agent.return_value = mock_agent

        response = client_without_mcp.post("/execute", json=sample_execution_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["result"] == "Agent executed successfully"

        # Verify agent was called with correct command
        mock_agent.run.assert_called_once_with("Test command for conductor agent")

    @patch('src.utils.mcp_utils.init_agent')
    def test_execute_with_input_payload(self, mock_init_agent, client_without_mcp):
        """Test execute endpoint with input payload format."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Input command executed")
        mock_init_agent.return_value = mock_agent

        payload = {"input": "Direct input command"}
        response = client_without_mcp.post("/execute", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["result"] == "Input command executed"

        mock_agent.run.assert_called_once_with("Direct input command")

    @patch('src.utils.mcp_utils.init_agent')
    def test_execute_with_command_payload(self, mock_init_agent, client_without_mcp):
        """Test execute endpoint with command payload format."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Command executed")
        mock_init_agent.return_value = mock_agent

        payload = {"command": "Direct command"}
        response = client_without_mcp.post("/execute", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        mock_agent.run.assert_called_once_with("Direct command")

    def test_execute_with_empty_payload(self, client_without_mcp):
        """Test execute endpoint with empty payload."""
        response = client_without_mcp.post("/execute", json={})

        assert response.status_code == 400
        assert "No command found in payload" in response.json()["detail"]

    def test_execute_with_empty_textentries(self, client_without_mcp):
        """Test execute endpoint with empty textEntries."""
        payload = {"textEntries": []}
        response = client_without_mcp.post("/execute", json=payload)

        assert response.status_code == 400

    @patch('src.utils.mcp_utils.init_agent')
    def test_execute_agent_exception(self, mock_init_agent, client_without_mcp, sample_execution_payload):
        """Test execute endpoint when agent raises an exception."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=Exception("Agent failed"))
        mock_init_agent.return_value = mock_agent

        response = client_without_mcp.post("/execute", json=sample_execution_payload)

        assert response.status_code == 500
        assert "Agent failed" in response.json()["detail"]


@pytest.mark.api
class TestSSEStreamingEndpoints:
    """Test SSE streaming endpoints."""

    @patch('src.utils.mcp_utils.init_agent')
    def test_start_execution_creates_job(self, mock_init_agent, client_without_mcp, sample_execution_payload):
        """Test that stream-execute creates a job and returns job_id."""
        mock_agent = AsyncMock()
        mock_init_agent.return_value = mock_agent

        response = client_without_mcp.post("/api/v1/stream-execute", json=sample_execution_payload)

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "started"
        assert "stream_url" in data
        assert data["job_id"].startswith("job_")

    def test_start_execution_with_invalid_payload(self, client_without_mcp):
        """Test stream-execute with invalid JSON payload."""
        response = client_without_mcp.post("/api/v1/stream-execute",
                                          data="invalid json",
                                          headers={"Content-Type": "application/json"})

        assert response.status_code == 422  # Unprocessable Entity

    def test_stream_events_nonexistent_job(self, client_without_mcp):
        """Test streaming events for non-existent job."""
        response = client_without_mcp.get("/api/v1/stream/nonexistent_job")

        assert response.status_code == 404
        assert "not found" in response.text

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.ACTIVE_STREAMS')
    def test_stream_events_with_queue(self, mock_streams, mock_init_agent, client_without_mcp):
        """Test streaming events when job queue exists."""
        # Setup mock queue with test event
        mock_queue = AsyncMock()
        test_event = {
            "event": "end_of_stream",
            "data": {"message": "Test completed"},
            "timestamp": 1234567890,
            "job_id": "test_job"
        }
        mock_queue.get = AsyncMock(return_value=test_event)
        mock_streams.__getitem__ = MagicMock(return_value=mock_queue)
        mock_streams.get = MagicMock(return_value=mock_queue)

        response = client_without_mcp.get("/api/v1/stream/test_job")

        # Should return 200 and stream should start
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


@pytest.mark.api
@pytest.mark.asyncio
class TestAsyncSSEStreaming:
    """Test SSE streaming with async client."""

    @patch('src.utils.mcp_utils.init_agent')
    async def test_stream_execution_flow(self, mock_init_agent, async_client_without_mcp, sample_execution_payload):
        """Test complete SSE execution flow."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Stream test result")
        mock_agent.on = MagicMock()
        mock_init_agent.return_value = mock_agent

        # Start execution
        response = await async_client_without_mcp.post("/api/v1/stream-execute", json=sample_execution_payload)
        assert response.status_code == 200

        data = response.json()
        job_id = data["job_id"]

        # Give some time for background task to start
        await asyncio.sleep(0.1)

        # Try to get stream (will timeout quickly in test)
        stream_response = await async_client_without_mcp.get(f"/api/v1/stream/{job_id}")
        assert stream_response.status_code == 200
        assert "text/event-stream" in stream_response.headers["content-type"]


@pytest.mark.api
class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client_without_mcp):
        """Test that CORS headers are present in responses."""
        response = client_without_mcp.options("/health")

        # Check for CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_preflight_request(self, client_without_mcp):
        """Test CORS preflight request."""
        response = client_without_mcp.options("/api/v1/stream-execute",
                                            headers={
                                                "Origin": "http://localhost:3000",
                                                "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "Content-Type"
                                            })

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "*"