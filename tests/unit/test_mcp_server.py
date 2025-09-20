"""
Tests for MCP Server functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.server.advanced_server import ConductorAdvancedMCPServer


@pytest.mark.mcp
class TestConductorAdvancedMCPServer:
    """Test ConductorAdvancedMCPServer functionality."""

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_server_initialization(self, mock_tools_class, mock_fastmcp_class):
        """Test MCP server initialization."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        server = ConductorAdvancedMCPServer(port=8006)

        assert server.port == 8006
        assert server.mcp == mock_fastmcp
        assert server.advanced_tools == mock_tools

        # Verify FastMCP was initialized with correct name and port
        mock_fastmcp_class.assert_called_once_with(name="ConductorAdvancedMCP", port=8006)

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_tool_registration(self, mock_tools_class, mock_fastmcp_class):
        """Test that all tools are registered with the MCP server."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp
        mock_fastmcp.tool.return_value = lambda func: func  # Mock decorator

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        ConductorAdvancedMCPServer(port=8006)

        # Verify that tool decorator was called for each expected tool
        expected_tools = [
            "list_available_agents",
            "get_agent_info",
            "validate_conductor_system",
            "execute_agent_stateless",
            "execute_agent_contextual",
            "start_interactive_session",
            "install_agent_templates",
            "backup_agents",
            "restore_agents",
            "migrate_storage",
            "set_environment",
            "get_system_config",
            "clear_agent_history",
        ]

        # Should be called once for each tool
        assert mock_fastmcp.tool.call_count == len(expected_tools)

        # Verify specific tool calls
        tool_calls = [call.kwargs for call in mock_fastmcp.tool.call_args_list]
        tool_names = [call["name"] for call in tool_calls]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_tool_descriptions(self, mock_tools_class, mock_fastmcp_class):
        """Test that tools have proper descriptions."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp
        mock_fastmcp.tool.return_value = lambda func: func

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        ConductorAdvancedMCPServer(port=8006)

        # Get all tool call arguments
        tool_calls = [call.kwargs for call in mock_fastmcp.tool.call_args_list]

        # Verify all tools have descriptions
        for call in tool_calls:
            assert "description" in call
            assert len(call["description"]) > 0
            assert isinstance(call["description"], str)

        # Check specific tool descriptions
        tool_descriptions = {call["name"]: call["description"] for call in tool_calls}

        assert "Lists all available agents" in tool_descriptions["list_available_agents"]
        assert "Execute an agent in stateless mode" in tool_descriptions["execute_agent_stateless"]
        assert (
            "Execute an agent in contextual mode" in tool_descriptions["execute_agent_contextual"]
        )

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_server_run(self, mock_tools_class, mock_fastmcp_class):
        """Test server run method."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        server = ConductorAdvancedMCPServer(port=8006)
        server.run(transport="sse")

        # Verify FastMCP run was called with correct transport
        mock_fastmcp.run.assert_called_once_with(transport="sse")

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_server_run_with_exception(self, mock_tools_class, mock_fastmcp_class):
        """Test server run method when FastMCP raises an exception."""
        mock_fastmcp = MagicMock()
        mock_fastmcp.run.side_effect = Exception("FastMCP failed to start")
        mock_fastmcp_class.return_value = mock_fastmcp

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        server = ConductorAdvancedMCPServer(port=8006)

        with pytest.raises(Exception, match="FastMCP failed to start"):
            server.run(transport="sse")

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_default_transport(self, mock_tools_class, mock_fastmcp_class):
        """Test server run with default transport."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        server = ConductorAdvancedMCPServer(port=8006)
        server.run()  # No transport specified

        # Should use default 'sse'
        mock_fastmcp.run.assert_called_once_with(transport="sse")


@pytest.mark.mcp
class TestMCPServerIntegration:
    """Test MCP server integration with tools."""

    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_tool_method_binding(self, mock_tools_class):
        """Test that tool methods are properly bound to the server."""
        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        # Setup mock methods
        mock_tools.list_available_agents = MagicMock(return_value="agents_list")
        mock_tools.execute_agent_stateless = MagicMock(return_value="execution_result")

        with patch("src.server.advanced_server.FastMCP") as mock_fastmcp_class:
            mock_fastmcp = MagicMock()
            mock_fastmcp_class.return_value = mock_fastmcp

            # Capture the functions passed to tool decorator
            decorated_functions = []

            def capture_tool_function(*args, **kwargs):
                def decorator(func):
                    decorated_functions.append((kwargs.get("name"), func))
                    return func

                return decorator

            mock_fastmcp.tool.side_effect = capture_tool_function

            ConductorAdvancedMCPServer(port=8006)

            # Find the captured functions
            tool_functions = dict(decorated_functions)

            # Verify that the tools' methods are bound correctly
            assert "list_available_agents" in tool_functions
            assert "execute_agent_stateless" in tool_functions

            # Test that calling the registered function calls the underlying tool method
            assert tool_functions["list_available_agents"] == mock_tools.list_available_agents
            assert tool_functions["execute_agent_stateless"] == mock_tools.execute_agent_stateless

    @patch("src.server.advanced_server.FastMCP")
    @patch("src.server.advanced_server.ConductorAdvancedTools")
    def test_server_port_configuration(self, mock_tools_class, mock_fastmcp_class):
        """Test server port configuration."""
        mock_fastmcp = MagicMock()
        mock_fastmcp_class.return_value = mock_fastmcp

        mock_tools = MagicMock()
        mock_tools_class.return_value = mock_tools

        # Test different port configurations
        for port in [8006, 9000, 8080]:
            server = ConductorAdvancedMCPServer(port=port)
            assert server.port == port
