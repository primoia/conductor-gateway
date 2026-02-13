"""
SSE Event Consumer for MCP Sidecar Tool Call Events.

Connects to /events SSE endpoints on MCP sidecars during agent executions
and broadcasts tool_call events to the frontend via WebSocket.
"""

import asyncio
import json
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Maximum concurrent SSE connections
MAX_SSE_CONNECTIONS = 10

# Timeout: close SSE after N seconds without events
SSE_IDLE_TIMEOUT = 300  # 5 minutes


class SSEEventConsumer:
    """
    Manages SSE connections to MCP sidecar /events endpoints.

    Lifecycle:
    1. When agent execution starts, call start_listening() with sidecar URLs
    2. Events are forwarded to a callback (typically WebSocket broadcast)
    3. When execution ends, call stop_listening() to clean up
    """

    def __init__(self, on_event_callback=None):
        """
        Args:
            on_event_callback: async callable(event_type: str, data: dict)
                             called for each received event
        """
        self._on_event = on_event_callback
        self._active_connections: dict[str, asyncio.Task] = {}  # key -> task
        self._semaphore = asyncio.Semaphore(MAX_SSE_CONNECTIONS)
        self._connection_count = 0

    async def start_listening(
        self,
        sidecar_urls: dict[str, str],
        session_id: Optional[str] = None,
        context: Optional[dict] = None
    ) -> list[str]:
        """
        Start listening to /events SSE on multiple sidecars.

        Args:
            sidecar_urls: dict of {mcp_name: host_url} (e.g., {"tasks": "http://localhost:13144"})
            session_id: Optional MCP session ID to filter events
            context: Additional context to include in forwarded events
                     (e.g., {"agent_id": "...", "instance_id": "...", "conversation_id": "..."})

        Returns:
            List of MCP names that were successfully connected
        """
        connected = []
        context = context or {}

        for mcp_name, base_url in sidecar_urls.items():
            # Build /events URL from the sidecar base URL
            # base_url might be like http://host:port/sse or http://host:port
            events_url = base_url.rstrip("/").replace("/sse", "") + "/events"
            if session_id:
                events_url += f"?session_id={session_id}"

            # Use task_id from context for unique key (supports concurrent executions)
            task_id = context.get("task_id", session_id or "all")
            key = f"{mcp_name}:{task_id}"

            # Skip if already connected to this exact sidecar+task combo
            if key in self._active_connections:
                logger.debug(f"Already connected to {mcp_name} events for task {task_id}")
                connected.append(mcp_name)
                continue

            # Check semaphore
            if self._connection_count >= MAX_SSE_CONNECTIONS:
                logger.warning(f"Max SSE connections ({MAX_SSE_CONNECTIONS}) reached, skipping {mcp_name}")
                continue

            # Start SSE listener task
            task = asyncio.create_task(
                self._listen_to_sidecar(key, mcp_name, events_url, context)
            )
            self._active_connections[key] = task
            self._connection_count += 1
            connected.append(mcp_name)
            logger.info(f"Started SSE listener for {mcp_name} at {events_url}")

        return connected

    async def stop_listening(self, mcp_name: Optional[str] = None, session_id: Optional[str] = None):
        """
        Stop listening to SSE events.

        Args:
            mcp_name: Stop specific MCP (None = stop all)
            session_id: Stop specific session
        """
        if mcp_name is None and session_id is None:
            # Stop all
            for key, task in list(self._active_connections.items()):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            self._active_connections.clear()
            self._connection_count = 0
            logger.info("Stopped all SSE listeners")
            return

        # Stop matching connections
        prefix = f"{mcp_name}:" if mcp_name else ""
        suffix = f":{session_id}" if session_id else ""

        to_remove = []
        for key, task in self._active_connections.items():
            if (not prefix or key.startswith(prefix)) and (not suffix or key.endswith(suffix)):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                to_remove.append(key)

        for key in to_remove:
            del self._active_connections[key]
            self._connection_count -= 1

        if to_remove:
            logger.info(f"Stopped SSE listeners: {to_remove}")

    async def _listen_to_sidecar(self, key: str, mcp_name: str, url: str, context: dict):
        """
        Internal: Listen to a single sidecar SSE stream with reconnection.
        """
        backoff = 1.0
        max_backoff = 30.0

        while True:
            try:
                async with self._semaphore:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(
                        connect=5.0,
                        read=SSE_IDLE_TIMEOUT + 60,  # allow for keepalives
                        write=5.0,
                        pool=5.0
                    )) as client:
                        async with client.stream("GET", url) as response:
                            if response.status_code != 200:
                                logger.warning(
                                    f"SSE {mcp_name}: HTTP {response.status_code}, retrying..."
                                )
                                await asyncio.sleep(backoff)
                                backoff = min(backoff * 2, max_backoff)
                                continue

                            logger.info(f"SSE {mcp_name}: Connected to {url}")
                            backoff = 1.0  # Reset backoff on successful connection
                            last_event_time = time.time()

                            async for line in response.aiter_lines():
                                # Check idle timeout
                                if time.time() - last_event_time > SSE_IDLE_TIMEOUT:
                                    logger.info(f"SSE {mcp_name}: Idle timeout, closing")
                                    return

                                # Parse SSE data lines
                                if line.startswith("data: "):
                                    last_event_time = time.time()
                                    try:
                                        event = json.loads(line[6:])
                                        await self._forward_event(mcp_name, event, context)
                                    except json.JSONDecodeError:
                                        logger.debug(f"SSE {mcp_name}: Non-JSON data: {line[:100]}")
                                elif line.startswith(":"):
                                    # Keepalive comment
                                    last_event_time = time.time()

            except asyncio.CancelledError:
                logger.info(f"SSE {mcp_name}: Listener cancelled")
                return
            except httpx.ConnectError:
                logger.warning(f"SSE {mcp_name}: Cannot connect to {url}, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                logger.warning(f"SSE {mcp_name}: Error: {e}, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    async def _forward_event(self, mcp_name: str, event: dict, context: dict):
        """Forward a received SSE event to the callback."""
        if not self._on_event:
            return

        # Enrich event with context
        enriched_data = {
            **event.get("data", {}),
            "mcp_name": mcp_name,
            **context
        }

        event_type = event.get("type", "unknown")

        try:
            await self._on_event("tool_call", {
                "phase": event_type.replace("tool_call_", ""),  # start, end, error
                **enriched_data
            })
        except Exception as e:
            logger.error(f"Error forwarding event from {mcp_name}: {e}")

    def get_stats(self) -> dict:
        """Get consumer statistics."""
        return {
            "active_connections": self._connection_count,
            "connections": list(self._active_connections.keys()),
            "max_connections": MAX_SSE_CONNECTIONS
        }
