"""
Service for dynamic MCP Service Mesh discovery.

Actively scans for available MCP sidecars on port ranges 13xxx,
pings their health endpoints, and maintains an internal cache of the live topology.
"""

import asyncio
import logging
from typing import Dict, List, Optional
import httpx
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class MeshNode(BaseModel):
    name: str
    url: str
    host_url: Optional[str] = None
    status: str
    latency_ms: Optional[float] = None
    tools_count: int = 0
    last_verified: datetime

class MCPMeshService:
    """Service for discovering and mapping the live MCP Mesh."""

    def __init__(self):
        self._mesh_cache: Dict[str, MeshNode] = {}
        self._is_running = False
        self._scan_task: Optional[asyncio.Task] = None
        # Ports to scan based on Primoia architecture (13000 to 13099)
        self._port_range = range(13000, 13100)
        # Using host.docker.internal for local docker discovery, could be configurable
        self._host = "host.docker.internal" 

    async def start_background_scan(self):
        """Starts the background task that periodically maps the mesh."""
        if self._is_running:
            return
        
        self._is_running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("📡 MCP Mesh Service started background scanner")

    async def stop_background_scan(self):
        """Stops the background scan task."""
        self._is_running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 MCP Mesh Service stopped background scanner")

    async def _scan_loop(self):
        """Infinite loop for periodic scanning."""
        while self._is_running:
            try:
                await self._refresh_mesh()
            except Exception as e:
                logger.error(f"Error in MCP Mesh scan loop: {e}", exc_info=True)
            
            # Wait 30 seconds before next scan
            await asyncio.sleep(30)

    async def _refresh_mesh(self):
        """Performs a full scan of the expected sidecar ports and updates cache."""
        logger.debug("Starting MCP Mesh topology scan...")
        live_nodes = {}
        
        # In a real distributed mesh, we might query Docker API or Kubernetes,
        # but for this specific "Dual Facade" architecture, probing known ports is robust.
        # To avoid blocking, we gather all requests concurrently
        tasks = []
        async with httpx.AsyncClient(timeout=3.0) as client:
            for port in self._port_range:
                # We probe the health endpoint of the sidecar
                url = f"http://{self._host}:{port}/health"
                tasks.append(self._probe_node(client, port, url))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, MeshNode):
                    live_nodes[result.name] = result

        self._mesh_cache = live_nodes
        logger.info(f"🕸️ MCP Mesh scanned: Found {len(self._mesh_cache)} live sidecars.")

    async def _probe_node(self, client: httpx.AsyncClient, port: int, url: str) -> Optional[MeshNode]:
        """Probes a specific port to see if an MCP Sidecar responds."""
        try:
            start_time = asyncio.get_event_loop().time()
            response = await client.get(url)
            
            # If we get a response, it's a sidecar
            if response.status_code == 200:
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                data = response.json()
                
                # We derive name from the sidecar's response or use port as fallback
                name = data.get("name", f"sidecar-{port}")
                tools_count = data.get("tools_count", 0)
                
                return MeshNode(
                    name=name,
                    url=f"http://{self._host}:{port}/sse", # Standard SSE endpoint
                    status="healthy",
                    latency_ms=round(latency_ms, 2),
                    tools_count=tools_count,
                    last_verified=datetime.utcnow()
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            # Port is closed or server is not responding (expected for most ports)
            return None
        except Exception as e:
            logger.debug(f"Unexpected error probing port {port}: {e}")
            return None

    def get_mesh_topology(self) -> List[MeshNode]:
        """Returns the current snapshot of the live MCP mesh."""
        return list(self._mesh_cache.values())
    
    def get_mesh_topology_as_dict(self) -> List[dict]:
        """Returns the current snapshot as dictionaries for API responses."""
        return [node.model_dump() for node in self._mesh_cache.values()]

# Global singleton instance
mesh_service = MCPMeshService()
