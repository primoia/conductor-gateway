"""
Conductor API Client - Encapsulates all communication with Conductor API
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ConductorClient:
    """Client for communicating with Conductor API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize Conductor client.

        Args:
            base_url: Base URL of the Conductor API
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        logger.info(f"ConductorClient initialized with base_url: {self.base_url}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def execute_agent(
        self,
        agent_name: str,
        prompt: str,
        instance_id: str | None = None,
        context_mode: str = "stateless",
        cwd: str | None = None,
        timeout: int = 300,
    ) -> dict[str, Any]:
        """
        Execute an agent via Conductor API.

        Args:
            agent_name: Name of the agent to execute
            prompt: Input text/prompt for the agent
            instance_id: Optional instance ID for stateful execution
            context_mode: Execution mode - "stateless" or "stateful"
            cwd: Working directory for execution
            timeout: Execution timeout in seconds

        Returns:
            Response from Conductor API

        Raises:
            httpx.HTTPStatusError: If the API returns an error
        """
        payload = {
            "agent_name": agent_name,
            "prompt": prompt,
            "context_mode": context_mode,
            "timeout": timeout,
        }

        if instance_id:
            payload["instance_id"] = instance_id

        if cwd:
            payload["cwd"] = cwd

        logger.info(
            f"Executing agent '{agent_name}' with context_mode='{context_mode}', "
            f"instance_id='{instance_id}'"
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/conductor/execute", json=payload
            )
            response.raise_for_status()
            result = response.json()

            logger.info(f"Agent '{agent_name}' executed successfully")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error executing agent '{agent_name}': {e.response.status_code} - "
                f"{e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error executing agent '{agent_name}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing agent '{agent_name}': {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """
        Check if Conductor API is healthy.

        Returns:
            Health status from Conductor API
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise
