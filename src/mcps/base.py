"""
Base class for MCP Servers.

All MCP servers should inherit from this class to ensure consistent behavior.
Each MCP server is self-contained and can be extracted to its own container later.
"""

import logging
from abc import ABC, abstractmethod

from mcp.server import FastMCP

logger = logging.getLogger(__name__)


class BaseMCPServer(ABC):
    """
    Base class for MCP servers.

    Each MCP server:
    - Runs on its own port
    - Exposes tools via SSE
    - Translates MCP calls to REST API calls (or internal operations)

    To create a new MCP server:
    1. Inherit from BaseMCPServer
    2. Implement _register_tools() to define your tools
    3. Add to MCP_REGISTRY in registry.py
    4. Add to MCPManager imports
    """

    def __init__(self, name: str, port: int, host: str = "0.0.0.0"):
        self.name = name
        self.port = port
        self.host = host
        self.mcp = FastMCP(name=name, port=port, host=host)

        # Register tools
        self._register_tools()

        logger.info(f"MCP Server '{name}' initialized on {host}:{port}")

    @abstractmethod
    def _register_tools(self) -> None:
        """
        Register tools with the MCP server.

        Override this method to define your MCP tools.
        Use self.mcp.tool() decorator to register tools.

        Example:
            @self.mcp.tool(name="my_tool", description="Does something")
            async def my_tool(param: str) -> dict:
                return {"result": "success"}
        """
        pass

    def run(self, transport: str = "sse") -> None:
        """
        Start the MCP server.

        Args:
            transport: Transport protocol to use ("sse" or "stdio")
        """
        try:
            logger.info(f"Starting MCP server '{self.name}' on {self.host}:{self.port} ({transport})")
            self.mcp.run(transport=transport)
        except Exception as e:
            logger.error(f"Failed to start MCP server '{self.name}': {e}", exc_info=True)
            raise
