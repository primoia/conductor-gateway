"""
Pytest configuration and shared fixtures.
"""
import asyncio
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """Mock configuration for tests."""
    return {
        "host": "127.0.0.1",
        "port": 5006,
        "mcp_port": 8006,
        "project_path": "/tmp/test_conductor",
        "conductor_server_mode": "advanced"
    }


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    config_content = """
server:
  host: "127.0.0.1"
  port: 5006
  mcp_port: 8006

conductor:
  project_path: "/tmp/test_conductor"
  conductor_server_mode: "advanced"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def mock_mcp_server():
    """Mock MCP server for testing."""
    with patch('src.server.advanced_server.ConductorAdvancedMCPServer') as mock:
        server_instance = MagicMock()
        server_instance.run = MagicMock()
        mock.return_value = server_instance
        yield server_instance


@pytest.fixture
def mock_agent():
    """Mock agent for testing."""
    agent = AsyncMock()
    agent.run = AsyncMock(return_value="Test agent response")
    agent.on = MagicMock()
    return agent


@pytest.fixture
def client_without_mcp():
    """Test client without MCP server startup."""
    with patch('src.api.app.start_mcp_server'):
        from src.api.app import create_app
        app = create_app()
        with TestClient(app) as client:
            yield client


@pytest.fixture
async def async_client_without_mcp():
    """Async test client without MCP server startup."""
    from httpx import AsyncClient
    from src.api.app import create_app

    with patch('src.api.app.start_mcp_server'):
        app = create_app()
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client


@pytest.fixture
def sample_execution_payload():
    """Sample payload for execution tests."""
    return {
        "textEntries": [
            {
                "content": "Test command for conductor agent",
                "type": "text"
            }
        ],
        "metadata": {
            "source": "test"
        }
    }


@pytest.fixture
def alternative_execution_payload():
    """Alternative payload format for execution tests."""
    return {
        "input": "Alternative test command",
        "command": "test_command"
    }