"""
MCP Servers module for Conductor Gateway.

This module provides multiple MCP servers that translate MCP tool calls
to REST API calls for various microservices.

Each MCP server runs on its own port:
- Prospector MCP: 5007
- Database MCP: 5008
- Conductor MCP: 5009
"""

from src.mcps.registry import MCP_REGISTRY, get_mcp_port, get_all_mcp_names
from src.mcps.mcp_manager import MCPManager

__all__ = [
    "MCP_REGISTRY",
    "get_mcp_port",
    "get_all_mcp_names",
    "MCPManager",
]
