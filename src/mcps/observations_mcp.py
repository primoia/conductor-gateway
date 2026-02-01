# src/mcps/observations_mcp.py
"""
Observations MCP Server.

This MCP server provides tools for agents to subscribe/unsubscribe from tasks
and get consolidated world state for injection into agent prompts.

Port: 5010
Target: http://conductor-api:8000
"""

import logging
from datetime import datetime
from typing import Any

import httpx

from src.mcps.base import BaseMCPServer
from src.mcps.registry import MCP_REGISTRY

logger = logging.getLogger(__name__)


class ObservationsMCP(BaseMCPServer):
    """
    MCP Server for task observations.

    Provides tools for:
    - Subscribing agents to observe tasks
    - Unsubscribing agents from tasks
    - Getting consolidated world state for agents
    - Listing agent observations
    """

    def __init__(self, port: int | None = None):
        config = MCP_REGISTRY["observations"]
        self.target_url = config["target_url"]
        self.timeout = 10.0  # Default timeout for observation operations

        super().__init__(
            name="observations",
            port=port or config["port"],
        )

        logger.info(f"ObservationsMCP initialized with API URL: {self.target_url}")

    def _register_tools(self) -> None:
        """Register observation tools."""

        @self.mcp.tool(
            name="get_agent_world_state",
            description="""Get consolidated world state for an agent.
            Returns the current state of all tasks the agent is observing.

            Parameters:
            - agent_id: The agent ID to get world state for (required)

            Returns consolidated world state with capabilities and their current status.""",
        )
        async def get_agent_world_state(agent_id: str) -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.target_url}/observations/{agent_id}/state")

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 404:
                        return {
                            "agent_id": agent_id,
                            "capabilities": [],
                            "timestamp": datetime.utcnow().isoformat(),
                            "message": "No observations found for this agent",
                        }
                    else:
                        return {
                            "error": f"Failed to get world state: {response.status_code}",
                            "detail": response.text,
                        }
            except Exception as e:
                logger.error(f"Error getting world state for {agent_id}: {e}")
                return {"error": str(e)}

        @self.mcp.tool(
            name="subscribe_agent_to_task",
            description="""Subscribe an agent to observe a task.
            The agent will receive updates about this task in its world state.

            Parameters:
            - agent_id: The agent ID to subscribe (required)
            - capability: Semantic name for this capability (e.g., 'observability', 'security') (required)
            - project_id: Project ID in Construction PM (required)
            - task_id: Task ID to observe (required)
            - description: Optional description for context
            - include_subtasks: Whether to include subtask details (default: false)

            Returns subscription confirmation.""",
        )
        async def subscribe_agent_to_task(
            agent_id: str,
            capability: str,
            project_id: int,
            task_id: int,
            description: str = "",
            include_subtasks: bool = False,
        ) -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.target_url}/observations/{agent_id}/subscribe",
                        json={
                            "capability": capability,
                            "project_id": project_id,
                            "task_id": task_id,
                            "description": description,
                            "include_subtasks": include_subtasks,
                        },
                    )

                    if response.status_code == 200:
                        return response.json()
                    else:
                        return {
                            "error": f"Failed to subscribe: {response.status_code}",
                            "detail": response.text,
                        }
            except Exception as e:
                logger.error(f"Error subscribing {agent_id} to task {task_id}: {e}")
                return {"error": str(e)}

        @self.mcp.tool(
            name="unsubscribe_agent_from_task",
            description="""Unsubscribe an agent from observing a task.

            Parameters:
            - agent_id: The agent ID to unsubscribe (required)
            - task_id: Task ID to stop observing (required)

            Returns unsubscription confirmation.""",
        )
        async def unsubscribe_agent_from_task(agent_id: str, task_id: int) -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.delete(
                        f"{self.target_url}/observations/{agent_id}/unsubscribe/{task_id}"
                    )

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 404:
                        return {
                            "status": "not_found",
                            "message": f"No subscription found for agent {agent_id} and task {task_id}",
                        }
                    else:
                        return {
                            "error": f"Failed to unsubscribe: {response.status_code}",
                            "detail": response.text,
                        }
            except Exception as e:
                logger.error(f"Error unsubscribing {agent_id} from task {task_id}: {e}")
                return {"error": str(e)}

        @self.mcp.tool(
            name="list_agent_observations",
            description="""List all tasks an agent is observing.

            Parameters:
            - agent_id: The agent ID to list observations for (required)

            Returns list of observations with task details.""",
        )
        async def list_agent_observations(agent_id: str) -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{self.target_url}/observations/{agent_id}")

                    if response.status_code == 200:
                        return response.json()
                    else:
                        return {
                            "error": f"Failed to list observations: {response.status_code}",
                            "detail": response.text,
                        }
            except Exception as e:
                logger.error(f"Error listing observations for {agent_id}: {e}")
                return {"error": str(e)}

        logger.info("Observations MCP tools registered")


# Allow running standalone for testing or future container extraction
if __name__ == "__main__":
    server = ObservationsMCP()
    server.run()
