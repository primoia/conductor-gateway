"""
Conductor MCP Server.

This MCP server provides tools for executing Conductor agents.
Translates MCP tool calls to Conductor API calls.

Port: 5009
Target: http://conductor-api:8000
"""

import logging
from typing import Any

import httpx

from src.mcps.base import BaseMCPServer
from src.mcps.registry import MCP_REGISTRY
from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)


class ConductorMCP(BaseMCPServer):
    """
    MCP Server for Conductor agent execution.

    Provides tools for:
    - Listing available agents
    - Executing agents (stateless and contextual)
    - Getting agent information
    - Managing agent sessions

    Uses the Conductor API for all operations.
    """

    def __init__(self, port: int | None = None):
        config = MCP_REGISTRY["conductor"]
        self.target_url = config["target_url"]
        self.timeout = CONDUCTOR_CONFIG.get("timeout", 1800)

        super().__init__(
            name="conductor",
            port=port or config["port"],
        )

        logger.info(f"ConductorMCP initialized with API URL: {self.target_url}")

    def _register_tools(self) -> None:
        """Register Conductor tools."""

        @self.mcp.tool(
            name="list_available_agents",
            description="""Lists all available agents in the Conductor system.

            Returns a list of all agents with their capabilities and tags.""",
        )
        async def list_available_agents() -> dict[str, Any]:
            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload={"list_agents": True},
            )

        @self.mcp.tool(
            name="get_agent_info",
            description="""Get detailed information about a specific agent.

            Parameters:
            - agent_id: The ID of the agent to get information for

            Returns complete agent information including capabilities, tags, and status.""",
        )
        async def get_agent_info(agent_id: str) -> dict[str, Any]:
            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload={"info_agent": agent_id},
            )

        @self.mcp.tool(
            name="execute_agent_stateless",
            description="""Execute a specific Conductor agent in stateless mode.

            Parameters:
            - agent_id: The exact ID/name of the agent to execute (required)
            - input_text: The input text for the agent (required)
            - cwd: The full file system path where the agent should work (required)
            - timeout: Execution timeout in seconds (default: 1800)
            - instance_id: Optional instance ID for context isolation

            Returns the agent's response.""",
        )
        async def execute_agent_stateless(
            agent_id: str,
            input_text: str,
            cwd: str,
            timeout: int = 1800,
            instance_id: str | None = None,
        ) -> dict[str, Any]:
            if not agent_id or not input_text or not cwd:
                return {"status": "error", "stderr": "agent_id, input_text e cwd são obrigatórios"}

            payload = {
                "agent_id": agent_id,
                "input_text": input_text,
                "cwd": cwd,
                "timeout": timeout,
                "chat": False,  # Stateless mode
            }

            if instance_id:
                payload["instance_id"] = instance_id

            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload=payload,
                timeout=timeout + 20,
            )

        @self.mcp.tool(
            name="execute_agent_contextual",
            description="""Execute an agent in contextual mode (with conversation history).

            Parameters:
            - agent_id: The ID of the agent to execute (required)
            - input_text: The input text for the agent (required)
            - timeout: Execution timeout in seconds (default: 1800)
            - clear_history: Whether to clear conversation history (default: False)
            - instance_id: Optional instance ID for context isolation

            Returns the agent's response while maintaining conversation context.""",
        )
        async def execute_agent_contextual(
            agent_id: str,
            input_text: str,
            timeout: int = 1800,
            clear_history: bool = False,
            instance_id: str | None = None,
        ) -> dict[str, Any]:
            payload = {
                "agent_id": agent_id,
                "input_text": input_text,
                "timeout": timeout,
                "chat": True,  # Contextual mode
                "clear_history": clear_history,
            }

            if instance_id:
                payload["instance_id"] = instance_id

            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload=payload,
                timeout=timeout + 20,
            )

        @self.mcp.tool(
            name="start_interactive_session",
            description="""Start an interactive session with an agent.

            Parameters:
            - agent_id: The ID of the agent to start session with (required)
            - initial_input: Optional initial input for the session
            - timeout: Session timeout in seconds (default: 1800)
            - instance_id: Optional instance ID for context isolation

            Returns session initialization result.""",
        )
        async def start_interactive_session(
            agent_id: str,
            initial_input: str | None = None,
            timeout: int = 1800,
            instance_id: str | None = None,
        ) -> dict[str, Any]:
            payload = {
                "agent_id": agent_id,
                "input_text": initial_input or "Iniciar sessão interativa",
                "timeout": timeout,
                "chat": True,
                "interactive": True,
            }

            if instance_id:
                payload["instance_id"] = instance_id

            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload=payload,
            )

        @self.mcp.tool(
            name="validate_conductor_system",
            description="""Validate the Conductor system configuration.

            Returns validation results and any configuration issues.""",
        )
        async def validate_conductor_system() -> dict[str, Any]:
            return await self._call_conductor_api(
                "/conductor/execute",
                method="POST",
                payload={"validate": True},
            )

        @self.mcp.tool(
            name="clear_agent_history",
            description="""Clear conversation history for a specific agent.

            Parameters:
            - agent_id: The ID of the agent to clear history for

            Returns history clearing results.""",
        )
        async def clear_agent_history(agent_id: str) -> dict[str, Any]:
            return await self._call_conductor_api(
                f"/sessions/{agent_id}/history",
                method="DELETE",
            )

        logger.info("Conductor MCP tools registered")

    async def _call_conductor_api(
        self,
        endpoint: str,
        method: str = "POST",
        payload: dict | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Make an async request to the Conductor API."""
        if timeout is None:
            timeout = self.timeout

        url = f"{self.target_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as client:
                logger.info(f"Calling Conductor API: {method} {url}")

                if method == "POST":
                    response = await client.post(url, json=payload)
                elif method == "GET":
                    response = await client.get(url, params=payload)
                elif method == "DELETE":
                    response = await client.delete(url)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                result = response.json()

                logger.info(f"Conductor API response: {response.status_code}")
                return result

        except httpx.TimeoutException:
            error_msg = f"Conductor API timeout after {timeout} seconds"
            logger.error(error_msg)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 124}

        except httpx.HTTPStatusError as e:
            error_msg = f"Conductor API error: {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "detail" in error_data:
                    error_msg = error_data["detail"]
            except Exception:
                error_msg = e.response.text or error_msg

            logger.error(f"Conductor API error: {error_msg}")
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 1}

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to Conductor: {e}"
            logger.error(error_msg)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 1}


# Allow running standalone for testing or future container extraction
if __name__ == "__main__":
    server = ConductorMCP()
    server.run()
