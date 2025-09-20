"""
Tests for utility functions.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestMCPUtils:
    """Test MCP utility functions."""

    @patch("src.utils.mcp_utils.MCPAgent")
    @patch("src.utils.mcp_utils.MCPClient")
    @patch("src.utils.mcp_utils.ChatOpenAI")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_init_agent_with_config(self, mock_llm, mock_client_class, mock_agent_class):
        """Test agent initialization with configuration."""
        from src.utils.mcp_utils import init_agent

        mock_client = MagicMock()
        mock_client_class.from_dict.return_value = mock_client

        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        agent_config = {
            "mcpServers": {
                "http": {"url": "http://localhost:8006/sse", "reconnect": True, "timeout": 30000}
            }
        }

        result = init_agent(agent_config=agent_config)

        assert result == mock_agent
        mock_client_class.from_dict.assert_called_once_with(agent_config)
        mock_agent_class.assert_called_once()

    @patch("src.utils.mcp_utils.MCPAgent")
    @patch("src.utils.mcp_utils.MCPClient")
    def test_init_agent_without_config(self, mock_client_class, mock_agent_class):
        """Test agent initialization without valid config."""
        from src.utils.mcp_utils import init_agent

        with pytest.raises(ValueError, match="A configuração do agente está incompleta ou vazia"):
            init_agent(agent_config=None)

    @patch("src.utils.mcp_utils.MCPClient")
    def test_init_agent_with_exception(self, mock_client_class):
        """Test agent initialization when MCPClient raises exception."""
        from src.utils.mcp_utils import init_agent

        mock_client_class.from_dict.side_effect = Exception("Failed to initialize MCPClient")

        agent_config = {"mcpServers": {"test": "config"}}

        with pytest.raises(Exception, match="Failed to initialize MCPClient"):
            init_agent(agent_config=agent_config)


@pytest.mark.unit
class TestImportStructure:
    """Test that imports work correctly."""

    def test_api_app_imports(self):
        """Test that API app imports work."""
        from src.api.app import create_app

        assert callable(create_app)

    def test_config_imports(self):
        """Test that config imports work."""
        from src.config.settings import CONDUCTOR_CONFIG, SERVER_CONFIG

        assert isinstance(SERVER_CONFIG, dict)
        assert isinstance(CONDUCTOR_CONFIG, dict)

    def test_server_imports(self):
        """Test that server imports work."""
        with patch("src.server.advanced_server.FastMCP"):
            with patch("src.server.advanced_server.ConductorAdvancedTools"):
                from src.server.advanced_server import ConductorAdvancedMCPServer

                assert ConductorAdvancedMCPServer is not None

    def test_main_imports(self):
        """Test that main module imports work."""
        with patch("src.main.start_mcp_server"):
            from src.main import main

            assert callable(main)


@pytest.mark.unit
class TestProjectStructure:
    """Test project structure and organization."""

    def test_src_directory_structure(self):
        """Test that expected source directories exist."""
        import os

        base_path = "/mnt/ramdisk/primoia-main/primoia-monorepo/projects/conductor-gateway"

        expected_dirs = [
            "src",
            "src/api",
            "src/config",
            "src/server",
            "src/tools",
            "src/utils",
            "tests",
            "tests/unit",
            "tests/integration",
        ]

        for directory in expected_dirs:
            full_path = os.path.join(base_path, directory)
            assert os.path.exists(full_path), f"Directory {directory} should exist"

    def test_essential_files_exist(self):
        """Test that essential project files exist."""
        import os

        base_path = "/mnt/ramdisk/primoia-main/primoia-monorepo/projects/conductor-gateway"

        expected_files = [
            "pyproject.toml",
            "src/main.py",
            "src/api/app.py",
            "src/config/settings.py",
            "src/server/advanced_server.py",
            "pytest.ini",
        ]

        for file_path in expected_files:
            full_path = os.path.join(base_path, file_path)
            assert os.path.exists(full_path), f"File {file_path} should exist"
