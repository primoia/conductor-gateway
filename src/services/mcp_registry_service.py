"""
Service layer for MCP Registry operations.

Manages registration, discovery, and health checking of MCP servers.
Combines internal MCPs (defined in code) with external MCPs (self-registered sidecars).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pymongo.collection import Collection
from pymongo.database import Database

from src.models.mcp_registry import (
    MCPType,
    MCPStatus,
    MCPMetadata,
    MCPRegisterRequest,
    MCPRegistryEntry,
    MCPRegistryEntryResponse,
    MCPHealthResponse,
    MCPServerConfig,
    MCPConfigResponse,
)
from src.mcps.registry import MCP_REGISTRY

logger = logging.getLogger(__name__)

# TTL for considering an MCP unhealthy (no heartbeat in this period)
HEARTBEAT_TTL_SECONDS = 90  # 3 missed heartbeats at 30s interval


class MCPRegistryService:
    """Service class for managing the MCP Registry."""

    COLLECTION_NAME = "mcp_registry"

    def __init__(self, db: Database):
        """
        Initialize the service with a MongoDB database.

        Args:
            db: PyMongo database instance
        """
        self.db = db
        self.collection: Collection = db[self.COLLECTION_NAME]
        self._ensure_indexes()
        self._sync_internal_mcps()

    def _ensure_indexes(self):
        """Create necessary indexes for the mcp_registry collection."""
        try:
            # Unique index on name
            self.collection.create_index("name", unique=True)
            logger.info("Created unique index on mcp_registry.name")

            # Index on type for filtering
            self.collection.create_index("type")
            logger.info("Created index on mcp_registry.type")

            # Index on status for filtering
            self.collection.create_index("status")
            logger.info("Created index on mcp_registry.status")

            # Index on last_heartbeat for TTL queries
            self.collection.create_index("last_heartbeat")
            logger.info("Created index on mcp_registry.last_heartbeat")

            # Compound index for category queries
            self.collection.create_index("metadata.category")
            logger.info("Created index on mcp_registry.metadata.category")

        except Exception as e:
            logger.warning(f"Index creation warning (may already exist): {e}")

    def _sync_internal_mcps(self):
        """Sync internal MCPs from MCP_REGISTRY to MongoDB."""
        try:
            for name, config in MCP_REGISTRY.items():
                port = config.get("port", 5000)
                description = config.get("description", "")

                entry = {
                    "name": name,
                    "type": MCPType.INTERNAL.value,
                    "url": f"http://localhost:{port}/sse",
                    "backend_url": config.get("target_url"),
                    "status": MCPStatus.UNKNOWN.value,
                    "tools_count": 0,
                    "last_heartbeat": None,
                    "registered_at": datetime.utcnow(),
                    "metadata": {
                        "category": "core",
                        "description": description,
                        "tags": ["internal", "core"]
                    }
                }

                # Upsert - update if exists, insert if not
                self.collection.update_one(
                    {"name": name},
                    {"$set": entry, "$setOnInsert": {"registered_at": datetime.utcnow()}},
                    upsert=True
                )
                logger.debug(f"Synced internal MCP: {name}")

            logger.info(f"Synced {len(MCP_REGISTRY)} internal MCPs to registry")

        except Exception as e:
            logger.error(f"Failed to sync internal MCPs: {e}", exc_info=True)

    def register(self, request: MCPRegisterRequest) -> MCPRegistryEntry:
        """
        Register a new external MCP server.

        Args:
            request: Registration request with MCP details

        Returns:
            The created registry entry

        Raises:
            ValueError: If MCP with same name already exists as internal
        """
        # Check if this is an internal MCP (cannot be overwritten)
        existing = self.collection.find_one({"name": request.name})
        if existing and existing.get("type") == MCPType.INTERNAL.value:
            raise ValueError(f"Cannot register '{request.name}': name reserved for internal MCP")

        now = datetime.utcnow()
        entry = {
            "name": request.name,
            "type": MCPType.EXTERNAL.value,
            "url": request.url,
            "host_url": request.host_url,
            "backend_url": request.backend_url,
            "auth": request.auth,
            "status": MCPStatus.HEALTHY.value,
            "tools_count": 0,
            "last_heartbeat": now,
            "registered_at": now,
            "metadata": request.metadata.model_dump() if request.metadata else {}
        }

        # Upsert - allows re-registration (e.g., after restart)
        self.collection.update_one(
            {"name": request.name},
            {"$set": entry},
            upsert=True
        )

        logger.info(f"Registered external MCP: {request.name} at {request.url}")
        return MCPRegistryEntry(**entry)

    def unregister(self, name: str) -> bool:
        """
        Unregister an MCP server.

        Args:
            name: Name of the MCP to unregister

        Returns:
            True if unregistered, False if not found

        Raises:
            ValueError: If trying to unregister an internal MCP
        """
        existing = self.collection.find_one({"name": name})
        if not existing:
            return False

        if existing.get("type") == MCPType.INTERNAL.value:
            raise ValueError(f"Cannot unregister '{name}': internal MCPs cannot be removed")

        result = self.collection.delete_one({"name": name})
        if result.deleted_count > 0:
            logger.info(f"Unregistered MCP: {name}")
            return True

        return False

    def heartbeat(self, name: str, tools_count: Optional[int] = None) -> bool:
        """
        Update heartbeat for an MCP server.

        Args:
            name: Name of the MCP
            tools_count: Optional updated tools count

        Returns:
            True if updated, False if not found
        """
        update = {
            "last_heartbeat": datetime.utcnow(),
            "status": MCPStatus.HEALTHY.value
        }
        if tools_count is not None:
            update["tools_count"] = tools_count

        result = self.collection.update_one(
            {"name": name},
            {"$set": update}
        )

        return result.modified_count > 0 or result.matched_count > 0

    def get_by_name(self, name: str) -> Optional[MCPRegistryEntryResponse]:
        """
        Get a single MCP entry by name.

        Args:
            name: Name of the MCP

        Returns:
            MCP entry or None if not found
        """
        doc = self.collection.find_one({"name": name})
        if not doc:
            return None

        # Check if status should be updated based on heartbeat TTL
        doc = self._check_heartbeat_status(doc)

        return MCPRegistryEntryResponse(
            name=doc["name"],
            type=MCPType(doc["type"]),
            url=doc["url"],
            backend_url=doc.get("backend_url"),
            status=MCPStatus(doc.get("status", "unknown")),
            tools_count=doc.get("tools_count", 0),
            last_heartbeat=doc.get("last_heartbeat"),
            registered_at=doc.get("registered_at"),
            metadata=MCPMetadata(**doc.get("metadata", {})) if doc.get("metadata") else None
        )

    def list_all(
        self,
        type_filter: Optional[MCPType] = None,
        category_filter: Optional[str] = None,
        status_filter: Optional[MCPStatus] = None,
        healthy_only: bool = False
    ) -> list[MCPRegistryEntryResponse]:
        """
        List all MCP entries with optional filters.

        Args:
            type_filter: Filter by type (internal/external)
            category_filter: Filter by category
            status_filter: Filter by status
            healthy_only: Only return healthy MCPs

        Returns:
            List of MCP entries
        """
        query = {}

        if type_filter:
            query["type"] = type_filter.value

        if category_filter:
            query["metadata.category"] = category_filter

        if status_filter:
            query["status"] = status_filter.value
        elif healthy_only:
            query["status"] = MCPStatus.HEALTHY.value

        cursor = self.collection.find(query).sort("name", 1)
        results = []

        for doc in cursor:
            doc = self._check_heartbeat_status(doc)
            results.append(MCPRegistryEntryResponse(
                name=doc["name"],
                type=MCPType(doc["type"]),
                url=doc["url"],
                backend_url=doc.get("backend_url"),
                status=MCPStatus(doc.get("status", "unknown")),
                tools_count=doc.get("tools_count", 0),
                last_heartbeat=doc.get("last_heartbeat"),
                registered_at=doc.get("registered_at"),
                metadata=MCPMetadata(**doc.get("metadata", {})) if doc.get("metadata") else None
            ))

        return results

    def _check_heartbeat_status(self, doc: dict) -> dict:
        """
        Check if MCP should be marked unhealthy based on heartbeat TTL.

        Args:
            doc: MongoDB document

        Returns:
            Updated document (may update status in DB)
        """
        if doc.get("type") == MCPType.INTERNAL.value:
            # Internal MCPs don't use heartbeat, they're always considered available
            return doc

        last_heartbeat = doc.get("last_heartbeat")
        if not last_heartbeat:
            return doc

        ttl_threshold = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TTL_SECONDS)

        if last_heartbeat < ttl_threshold and doc.get("status") == MCPStatus.HEALTHY.value:
            # Mark as unhealthy
            self.collection.update_one(
                {"name": doc["name"]},
                {"$set": {"status": MCPStatus.UNHEALTHY.value}}
            )
            doc["status"] = MCPStatus.UNHEALTHY.value
            logger.warning(f"MCP '{doc['name']}' marked unhealthy (no heartbeat since {last_heartbeat})")

        return doc

    def resolve_names(self, names: list[str]) -> tuple[dict[str, str], list[str]]:
        """
        Resolve a list of MCP names to their URLs.

        Args:
            names: List of MCP names to resolve

        Returns:
            Tuple of (resolved dict, not_found list)
        """
        resolved = {}
        not_found = []

        for name in names:
            doc = self.collection.find_one({"name": name})
            if doc and doc.get("status") != MCPStatus.UNHEALTHY.value:
                resolved[name] = doc["url"]
            else:
                not_found.append(name)

        return resolved, not_found

    async def check_health(self, name: str, timeout: float = 5.0) -> MCPHealthResponse:
        """
        Actively check health of an MCP server.

        Args:
            name: Name of the MCP to check
            timeout: Request timeout in seconds

        Returns:
            Health check response
        """
        entry = self.get_by_name(name)
        if not entry:
            return MCPHealthResponse(
                name=name,
                status=MCPStatus.UNKNOWN,
                error="MCP not found in registry"
            )

        try:
            start = asyncio.get_event_loop().time()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Try to connect to SSE endpoint
                response = await client.get(entry.url.replace("/sse", "/health"))

                latency_ms = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code == 200:
                    # Update status in registry
                    self.collection.update_one(
                        {"name": name},
                        {"$set": {
                            "status": MCPStatus.HEALTHY.value,
                            "last_heartbeat": datetime.utcnow()
                        }}
                    )
                    return MCPHealthResponse(
                        name=name,
                        status=MCPStatus.HEALTHY,
                        latency_ms=round(latency_ms, 2),
                        tools_count=entry.tools_count,
                        last_heartbeat=datetime.utcnow()
                    )
                else:
                    return MCPHealthResponse(
                        name=name,
                        status=MCPStatus.UNHEALTHY,
                        latency_ms=round(latency_ms, 2),
                        error=f"HTTP {response.status_code}"
                    )

        except httpx.TimeoutException:
            self._mark_unhealthy(name)
            return MCPHealthResponse(
                name=name,
                status=MCPStatus.UNHEALTHY,
                error="Connection timeout"
            )
        except Exception as e:
            self._mark_unhealthy(name)
            return MCPHealthResponse(
                name=name,
                status=MCPStatus.UNHEALTHY,
                error=str(e)
            )

    def _mark_unhealthy(self, name: str):
        """Mark an MCP as unhealthy."""
        self.collection.update_one(
            {"name": name},
            {"$set": {"status": MCPStatus.UNHEALTHY.value}}
        )

    def get_stats(self) -> dict:
        """
        Get registry statistics.

        Returns:
            Dict with counts by type and status
        """
        pipeline = [
            {
                "$group": {
                    "_id": {"type": "$type", "status": "$status"},
                    "count": {"$sum": 1}
                }
            }
        ]

        results = list(self.collection.aggregate(pipeline))

        stats = {
            "total": 0,
            "internal": 0,
            "external": 0,
            "healthy": 0,
            "unhealthy": 0,
            "unknown": 0
        }

        for r in results:
            count = r["count"]
            stats["total"] += count

            if r["_id"]["type"] == MCPType.INTERNAL.value:
                stats["internal"] += count
            else:
                stats["external"] += count

            status = r["_id"].get("status", "unknown")
            if status in stats:
                stats[status] += count

        return stats

    def cleanup_stale_entries(self, max_age_hours: int = 24) -> int:
        """
        Remove external MCP entries that haven't sent heartbeat in a long time.

        Args:
            max_age_hours: Maximum age in hours since last heartbeat

        Returns:
            Number of entries removed
        """
        threshold = datetime.utcnow() - timedelta(hours=max_age_hours)

        result = self.collection.delete_many({
            "type": MCPType.EXTERNAL.value,
            "last_heartbeat": {"$lt": threshold}
        })

        if result.deleted_count > 0:
            logger.info(f"Cleaned up {result.deleted_count} stale MCP entries")

        return result.deleted_count

    def get_mcp_config(
        self,
        instance_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> MCPConfigResponse:
        """
        Get MCP config in Claude CLI format for an agent or instance.

        Combines MCPs from:
        1. Agent template (definition.mcp_configs)
        2. Instance extras (instance.mcp_configs)

        Args:
            instance_id: Agent instance ID
            agent_id: Agent template ID

        Returns:
            MCPConfigResponse with mcpServers dict ready for Claude CLI
        """
        mcp_names: set[str] = set()

        # Get agents and instances collections
        agents_collection = self.db["agents"]
        instances_collection = self.db["agent_instances"]

        # 1. If instance_id provided, get instance and its agent
        if instance_id:
            instance = instances_collection.find_one({"instance_id": instance_id})
            if instance:
                # Get MCPs from instance
                instance_mcps = instance.get("mcp_configs", [])
                mcp_names.update(instance_mcps)
                logger.debug(f"Instance {instance_id} MCPs: {instance_mcps}")

                # Get agent_id from instance if not provided
                if not agent_id:
                    agent_id = instance.get("agent_id")

        # 2. Get MCPs from agent template
        if agent_id:
            agent = agents_collection.find_one({"agent_id": agent_id})
            if agent:
                # MCPs can be in definition.mcp_configs or top-level mcp_configs
                definition = agent.get("definition", {})
                agent_mcps = definition.get("mcp_configs", []) or agent.get("mcp_configs", [])
                mcp_names.update(agent_mcps)
                logger.debug(f"Agent {agent_id} MCPs: {agent_mcps}")

        if not mcp_names:
            logger.info(f"No MCPs configured for instance={instance_id}, agent={agent_id}")
            return MCPConfigResponse(mcpServers={})

        # 3. Resolve MCPs from registry
        mcp_servers: dict[str, MCPServerConfig] = {}

        for name in mcp_names:
            doc = self.collection.find_one({"name": name})
            if doc and doc.get("status") != MCPStatus.UNHEALTHY.value:
                # Usar host_url (para Claude CLI no host) se disponível, senão url
                url = doc.get("host_url") or doc["url"]
                auth = doc.get("auth")

                # Append auth to URL if present
                if auth:
                    separator = "&" if "?" in url else "?"
                    url = f"{url}{separator}auth={auth}"

                mcp_servers[name] = MCPServerConfig(type="sse", url=url)
                logger.debug(f"Resolved MCP {name}: {url}")
            else:
                logger.warning(f"MCP {name} not found or unhealthy in registry")

        logger.info(f"Built MCP config with {len(mcp_servers)} servers for instance={instance_id}, agent={agent_id}")
        return MCPConfigResponse(mcpServers=mcp_servers)
