"""
MCP Manager - Manages multiple MCP servers running in threads.

This manager starts all registered MCP servers in separate daemon threads.
Each MCP server runs on its own port and exposes tools via SSE.
"""

import logging
import threading
from typing import TYPE_CHECKING

from src.mcps.registry import MCP_REGISTRY, get_mcp_port

if TYPE_CHECKING:
    from src.mcps.base import BaseMCPServer

logger = logging.getLogger(__name__)


class MCPManager:
    """
    Manages multiple MCP servers running in threads.

    Usage:
        manager = MCPManager()
        manager.start_all()  # Start all MCPs in daemon threads

    The manager lazily imports MCP server classes to avoid circular imports.
    """

    def __init__(self):
        self.threads: dict[str, threading.Thread] = {}
        self.servers: dict[str, "BaseMCPServer"] = {}
        self._started = False

    def _get_mcp_class(self, name: str):
        """
        Lazily import and return the MCP server class for a given name.

        This avoids circular imports by importing only when needed.
        """
        if name == "prospector":
            from src.mcps.prospector_mcp import ProspectorMCP
            return ProspectorMCP
        elif name == "database":
            from src.mcps.database_mcp import DatabaseMCP
            return DatabaseMCP
        elif name == "conductor":
            from src.mcps.conductor_mcp import ConductorMCP
            return ConductorMCP
        else:
            raise ValueError(f"Unknown MCP: {name}")

    def start_mcp(self, name: str) -> bool:
        """
        Start a single MCP server in a daemon thread.

        Args:
            name: Name of the MCP to start (must be in MCP_REGISTRY)

        Returns:
            True if started successfully, False otherwise
        """
        if name not in MCP_REGISTRY:
            logger.error(f"MCP '{name}' not found in registry")
            return False

        if name in self.threads and self.threads[name].is_alive():
            logger.warning(f"MCP '{name}' is already running")
            return True

        try:
            config = MCP_REGISTRY[name]
            mcp_class = self._get_mcp_class(name)
            server = mcp_class(port=config["port"])

            thread = threading.Thread(
                target=server.run,
                kwargs={"transport": "sse"},
                daemon=True,
                name=f"MCP-{name}",
            )
            thread.start()

            self.threads[name] = thread
            self.servers[name] = server

            logger.info(f"MCP '{name}' started on port {config['port']}")
            return True

        except Exception as e:
            logger.error(f"Failed to start MCP '{name}': {e}", exc_info=True)
            return False

    def start_all(self) -> dict[str, bool]:
        """
        Start all registered MCP servers in daemon threads.

        Returns:
            Dict mapping MCP names to success status
        """
        if self._started:
            logger.warning("MCPManager.start_all() called more than once")
            return {name: name in self.threads for name in MCP_REGISTRY}

        results = {}
        for name in MCP_REGISTRY:
            results[name] = self.start_mcp(name)

        self._started = True

        # Log summary
        started = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"MCPManager: Started {started}/{total} MCP servers")

        return results

    def get_status(self) -> dict[str, dict]:
        """
        Get status of all MCP servers.

        Returns:
            Dict with status info for each MCP
        """
        status = {}
        for name, config in MCP_REGISTRY.items():
            thread = self.threads.get(name)
            status[name] = {
                "port": config["port"],
                "running": thread.is_alive() if thread else False,
                "description": config["description"],
            }
        return status

    def get_mcp_urls(self, host: str = "localhost") -> dict[str, str]:
        """
        Get SSE URLs for all running MCPs.

        Args:
            host: Host to use in URLs (default: localhost)

        Returns:
            Dict mapping MCP names to their SSE URLs
        """
        urls = {}
        for name, config in MCP_REGISTRY.items():
            thread = self.threads.get(name)
            if thread and thread.is_alive():
                urls[name] = f"http://{host}:{config['port']}/sse"
        return urls

    def generate_mcp_config(self, host: str = "localhost") -> dict:
        """
        Generate MCP config JSON for Claude CLI.

        Args:
            host: Host to use in URLs (default: localhost)

        Returns:
            Dict in Claude CLI mcp-config format
        """
        mcp_servers = {}
        for name, url in self.get_mcp_urls(host).items():
            mcp_servers[name] = {
                "url": url,
                "transport": "sse",
            }
        return {"mcpServers": mcp_servers}
