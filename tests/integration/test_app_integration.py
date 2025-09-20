"""
Integration tests for the complete application.
"""
import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.integration
class TestApplicationLifespan:
    """Test application lifespan management."""

    @patch('src.api.app.start_mcp_server')
    def test_app_creation_without_mcp_startup(self, mock_start_mcp):
        """Test app creation without actually starting MCP server."""
        from src.api.app import create_app

        app = create_app()

        # Verify app is created successfully
        assert app.title == "Conductor Gateway API"
        assert app.version == "3.1.0"
        assert app.description == "Bridge service for integrating primoia-browse-use with conductor project"

        # Check that routes are registered
        routes = [route.path for route in app.routes]
        assert "/health" in routes
        assert "/execute" in routes
        assert "/api/v1/stream-execute" in routes
        assert "/api/v1/stream/{job_id}" in routes

    @patch('src.api.app.start_mcp_server')
    def test_cors_middleware_enabled(self, mock_start_mcp):
        """Test that CORS middleware is properly configured."""
        from src.api.app import create_app

        app = create_app()

        # Verify CORS middleware is in the middleware stack
        middleware_classes = [middleware.__class__.__name__ for middleware in app.middleware]
        assert "CORSMiddleware" in middleware_classes


@pytest.mark.integration
class TestEndToEndExecution:
    """Test end-to-end execution flows."""

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.start_mcp_server')
    def test_synchronous_execution_end_to_end(self, mock_start_mcp, mock_init_agent, sample_execution_payload):
        """Test complete synchronous execution flow."""
        # Setup mocks
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="End-to-end test successful")
        mock_init_agent.return_value = mock_agent

        # Create app and client
        from src.api.app import create_app
        app = create_app()

        with TestClient(app) as client:
            # Execute command
            response = client.post("/execute", json=sample_execution_payload)

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["result"] == "End-to-end test successful"

            # Verify agent was initialized with correct config
            mock_init_agent.assert_called_once()
            agent_config = mock_init_agent.call_args[1]["agent_config"]
            assert "mcpServers" in agent_config
            assert "http" in agent_config["mcpServers"]

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.start_mcp_server')
    def test_streaming_execution_initialization(self, mock_start_mcp, mock_init_agent, sample_execution_payload):
        """Test streaming execution initialization."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Streaming test result")
        mock_agent.on = MagicMock()
        mock_init_agent.return_value = mock_agent

        from src.api.app import create_app
        app = create_app()

        with TestClient(app) as client:
            # Start streaming execution
            response = client.post("/api/v1/stream-execute", json=sample_execution_payload)

            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "started"
            assert "/api/v1/stream/" in data["stream_url"]

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.start_mcp_server')
    def test_multiple_payload_formats(self, mock_start_mcp, mock_init_agent):
        """Test that different payload formats work correctly."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Format test successful")
        mock_init_agent.return_value = mock_agent

        from src.api.app import create_app
        app = create_app()

        payloads = [
            {"textEntries": [{"content": "Text entry command"}]},
            {"input": "Input command"},
            {"command": "Direct command"}
        ]

        expected_commands = [
            "Text entry command",
            "Input command",
            "Direct command"
        ]

        with TestClient(app) as client:
            for payload, expected_cmd in zip(payloads, expected_commands):
                mock_agent.run.reset_mock()

                response = client.post("/execute", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"

                # Verify correct command was extracted
                mock_agent.run.assert_called_once_with(expected_cmd)


@pytest.mark.integration
@pytest.mark.slow
class TestSSEStreamingIntegration:
    """Test SSE streaming integration (marked as slow tests)."""

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.start_mcp_server')
    @pytest.mark.asyncio
    async def test_sse_event_flow(self, mock_start_mcp, mock_init_agent, sample_execution_payload):
        """Test SSE event generation flow."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="SSE test result")
        mock_agent.on = MagicMock()
        mock_init_agent.return_value = mock_agent

        from src.api.app import create_app
        app = create_app()

        async with AsyncClient(app=app, base_url="http://test") as client:
            # Start execution
            response = await client.post("/api/v1/stream-execute", json=sample_execution_payload)
            assert response.status_code == 200

            job_data = response.json()
            job_id = job_data["job_id"]

            # Allow background task to start
            await asyncio.sleep(0.1)

            # Test stream endpoint exists
            stream_response = await client.get(f"/api/v1/stream/{job_id}")
            assert stream_response.status_code == 200
            assert "text/event-stream" in stream_response.headers["content-type"]

    @patch('src.utils.mcp_utils.init_agent')
    @patch('src.api.app.start_mcp_server')
    def test_concurrent_streaming_jobs(self, mock_start_mcp, mock_init_agent, sample_execution_payload):
        """Test multiple concurrent streaming jobs."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value="Concurrent test result")
        mock_agent.on = MagicMock()
        mock_init_agent.return_value = mock_agent

        from src.api.app import create_app
        app = create_app()

        with TestClient(app) as client:
            job_ids = []

            # Start multiple jobs
            for i in range(3):
                payload = {
                    "textEntries": [{"content": f"Concurrent command {i}"}]
                }
                response = client.post("/api/v1/stream-execute", json=payload)
                assert response.status_code == 200
                job_ids.append(response.json()["job_id"])

            # Verify all jobs have unique IDs
            assert len(set(job_ids)) == 3

            # Verify all job streams can be accessed
            for job_id in job_ids:
                response = client.get(f"/api/v1/stream/{job_id}")
                # Should either return 200 (stream active) or 404 (completed/not found)
                assert response.status_code in [200, 404]


@pytest.mark.integration
class TestConfigurationIntegration:
    """Test configuration integration with the application."""

    @patch('src.api.app.start_mcp_server')
    def test_health_endpoint_shows_config_info(self, mock_start_mcp):
        """Test that health endpoint shows configuration information."""
        from src.api.app import create_app
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()

            # Verify configuration info is included
            assert "endpoints" in data
            assert "api" in data["endpoints"]
            assert "mcp" in data["endpoints"]
            assert "health" in data["endpoints"]

            # Verify URLs contain expected ports
            assert ":5006" in data["endpoints"]["api"]
            assert ":8006" in data["endpoints"]["mcp"]
            assert ":5006" in data["endpoints"]["health"]

    @patch.dict('os.environ', {
        'CONDUCTOR_GATEWAY_HOST': 'test.example.com',
        'CONDUCTOR_GATEWAY_PORT': '9999'
    })
    @patch('src.api.app.start_mcp_server')
    def test_environment_override_in_health(self, mock_start_mcp):
        """Test that environment variable overrides appear in health endpoint."""
        # Reload config with environment variables
        with patch('src.config.settings.CONFIG_FILE', '/nonexistent/config.yaml'):
            from src.config.settings import load_config
            config = load_config()

            # Patch SERVER_CONFIG to use the new config
            with patch('src.config.settings.SERVER_CONFIG', config["server"]):
                from src.api.app import create_app
                app = create_app()

                with TestClient(app) as client:
                    response = client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    # Should reflect environment variable overrides
                    assert "test.example.com:9999" in data["endpoints"]["api"]