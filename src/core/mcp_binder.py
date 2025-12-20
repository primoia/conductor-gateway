"""
MCP Binder - Core component for managing agent-MCP bindings.

The Binder is the "kernel" of the MCP system, responsible for:
- Binding MCPs to agent instances before execution
- Unbinding when agents finish
- Dynamic add/remove of MCPs during execution
- Health monitoring of bound MCPs
- Enforcing security policies

This is a hardcore component that runs inside the Gateway.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
import yaml
from pathlib import Path
from pymongo.database import Database

from src.models.mcp_binder import (
    BindingStatus,
    MCPBinding,
    MCPBindingEntry,
    BindRequest,
    BindResponse,
    BindingPolicy,
)
from src.services.mcp_registry_service import MCPRegistryService

logger = logging.getLogger(__name__)


class MCPBinder:
    """
    Core MCP Binder component.

    Manages the lifecycle of agent-MCP bindings:
    - BIND: Resolve and connect MCPs before agent runs
    - UNBIND: Disconnect MCPs when agent finishes
    - ADD_MCP: Add MCP to running agent
    - REMOVE_MCP: Remove MCP from running agent
    - REBIND: Reconnect after MCP failure

    This component is initialized at Gateway startup and remains active.
    """

    def __init__(
        self,
        registry_service: MCPRegistryService,
        db: Optional[Database] = None,
        agents_config_path: Optional[str] = None,
    ):
        """
        Initialize the MCP Binder.

        Args:
            registry_service: MCP Registry service for resolving names to URLs
            db: MongoDB database for persisting bindings (optional)
            agents_config_path: Path to agents config directory
        """
        self.registry = registry_service
        self.db = db
        self.agents_config_path = agents_config_path or "/mnt/ramdisk/primoia-main/primoia/conductor-community/conductor/conductor/config/agents"

        # In-memory binding table (source of truth for active bindings)
        self._bindings: dict[str, MCPBinding] = {}

        # Policies cache
        self._policies: dict[str, BindingPolicy] = {}

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

        # Default policy for agents without explicit policy
        self._default_policy = BindingPolicy(
            agent_id="*",
            allowed_mcps=["*"],
            denied_mcps=[],
            max_concurrent_mcps=10,
            require_healthy=True,
        )

        logger.info("MCPBinder initialized")

    # =========================================================================
    # BIND Operations
    # =========================================================================

    async def bind(self, request: BindRequest) -> BindResponse:
        """
        Bind MCPs to an agent instance.

        This is called before an agent starts execution.

        Args:
            request: Bind request with instance_id, agent_id, and optional mcp_names

        Returns:
            BindResponse with mcpServers config for MCPClient
        """
        instance_id = request.instance_id
        agent_id = request.agent_id

        logger.info(f"[BINDER] Binding MCPs for instance={instance_id}, agent={agent_id}")

        # Check if already bound
        if instance_id in self._bindings:
            existing = self._bindings[instance_id]
            logger.warning(f"[BINDER] Instance {instance_id} already bound, returning existing")
            return BindResponse(
                success=True,
                instance_id=instance_id,
                bound_mcps=existing.get_active_mcp_names(),
                mcp_servers_config=existing.get_mcp_servers_config(),
                message="Already bound"
            )

        # Get MCP names to bind
        mcp_names = request.mcp_names
        if not mcp_names:
            # Read from agent definition
            mcp_names = self._get_agent_mcp_configs(agent_id)

        if not mcp_names:
            logger.warning(f"[BINDER] No MCPs configured for agent {agent_id}")
            # Create empty binding (agent can still run, just no MCP tools)
            binding = MCPBinding(
                instance_id=instance_id,
                agent_id=agent_id,
                conversation_id=request.conversation_id,
                screenplay_id=request.screenplay_id,
                status=BindingStatus.ACTIVE,
            )
            self._bindings[instance_id] = binding

            return BindResponse(
                success=True,
                instance_id=instance_id,
                bound_mcps=[],
                mcp_servers_config={"mcpServers": {}},
                message="No MCPs configured for this agent"
            )

        # Apply policy
        policy = self._get_policy(agent_id)
        mcp_names = [name for name in mcp_names if policy.is_allowed(name)]

        if len(mcp_names) > policy.max_concurrent_mcps:
            mcp_names = mcp_names[:policy.max_concurrent_mcps]
            logger.warning(f"[BINDER] Truncated MCPs to {policy.max_concurrent_mcps} per policy")

        # Resolve MCP names to URLs
        resolved, not_found = self.registry.resolve_names(mcp_names)

        if not_found:
            logger.warning(f"[BINDER] MCPs not found in registry: {not_found}")

        # Health check if required by policy
        healthy_mcps = {}
        failed_mcps = list(not_found)

        for name, url in resolved.items():
            if policy.require_healthy:
                is_healthy = await self._check_mcp_health(name, url)
                if is_healthy:
                    healthy_mcps[name] = url
                else:
                    failed_mcps.append(name)
                    logger.warning(f"[BINDER] MCP {name} failed health check")
            else:
                healthy_mcps[name] = url

        # Create binding
        binding = MCPBinding(
            instance_id=instance_id,
            agent_id=agent_id,
            conversation_id=request.conversation_id,
            screenplay_id=request.screenplay_id,
            status=BindingStatus.ACTIVE,
        )

        for name, url in healthy_mcps.items():
            binding.mcps[name] = MCPBindingEntry(name=name, url=url)

        # Store binding
        self._bindings[instance_id] = binding

        # Persist to MongoDB if available
        if self.db:
            await self._persist_binding(binding)

        logger.info(f"[BINDER] Bound {len(healthy_mcps)} MCPs for instance {instance_id}: {list(healthy_mcps.keys())}")

        return BindResponse(
            success=True,
            instance_id=instance_id,
            bound_mcps=list(healthy_mcps.keys()),
            failed_mcps=failed_mcps,
            mcp_servers_config=binding.get_mcp_servers_config(),
        )

    async def unbind(self, instance_id: str, reason: str = None) -> bool:
        """
        Unbind all MCPs from an agent instance.

        This is called when an agent finishes execution.

        Args:
            instance_id: The agent instance ID
            reason: Optional reason for unbinding

        Returns:
            True if unbound successfully
        """
        if instance_id not in self._bindings:
            logger.warning(f"[BINDER] Cannot unbind {instance_id}: not found")
            return False

        binding = self._bindings[instance_id]
        binding.status = BindingStatus.UNBOUND
        binding.updated_at = datetime.utcnow()

        # Log metrics
        logger.info(
            f"[BINDER] Unbound instance {instance_id}: "
            f"mcps={list(binding.mcps.keys())}, "
            f"tool_calls={binding.total_tool_calls}, "
            f"reason={reason}"
        )

        # Persist final state if using MongoDB
        if self.db:
            await self._persist_binding(binding)

        # Remove from active bindings
        del self._bindings[instance_id]

        return True

    # =========================================================================
    # Dynamic MCP Operations
    # =========================================================================

    async def add_mcp(self, instance_id: str, mcp_name: str) -> bool:
        """
        Add an MCP to a running agent instance.

        Args:
            instance_id: The agent instance ID
            mcp_name: MCP name to add

        Returns:
            True if added successfully
        """
        if instance_id not in self._bindings:
            logger.error(f"[BINDER] Cannot add MCP: instance {instance_id} not bound")
            return False

        binding = self._bindings[instance_id]

        # Check policy
        policy = self._get_policy(binding.agent_id)
        if not policy.is_allowed(mcp_name):
            logger.warning(f"[BINDER] MCP {mcp_name} not allowed by policy for {binding.agent_id}")
            return False

        if len(binding.mcps) >= policy.max_concurrent_mcps:
            logger.warning(f"[BINDER] Cannot add MCP: max concurrent MCPs reached")
            return False

        # Resolve
        resolved, not_found = self.registry.resolve_names([mcp_name])
        if mcp_name in not_found:
            logger.error(f"[BINDER] MCP {mcp_name} not found in registry")
            return False

        url = resolved[mcp_name]

        # Health check
        if policy.require_healthy:
            is_healthy = await self._check_mcp_health(mcp_name, url)
            if not is_healthy:
                logger.error(f"[BINDER] MCP {mcp_name} failed health check")
                return False

        # Add to binding
        success = binding.add_mcp(mcp_name, url)
        if success:
            logger.info(f"[BINDER] Added MCP {mcp_name} to instance {instance_id}")

            if self.db:
                await self._persist_binding(binding)

        return success

    async def remove_mcp(self, instance_id: str, mcp_name: str, reason: str = None) -> bool:
        """
        Remove an MCP from a running agent instance.

        Args:
            instance_id: The agent instance ID
            mcp_name: MCP name to remove
            reason: Optional reason

        Returns:
            True if removed successfully
        """
        if instance_id not in self._bindings:
            logger.error(f"[BINDER] Cannot remove MCP: instance {instance_id} not bound")
            return False

        binding = self._bindings[instance_id]
        success = binding.remove_mcp(mcp_name)

        if success:
            logger.info(f"[BINDER] Removed MCP {mcp_name} from instance {instance_id}, reason={reason}")

            if self.db:
                await self._persist_binding(binding)

        return success

    async def rebind(self, instance_id: str) -> BindResponse:
        """
        Rebind MCPs for an instance (e.g., after MCP recovery).

        Args:
            instance_id: The agent instance ID

        Returns:
            BindResponse with updated config
        """
        if instance_id not in self._bindings:
            logger.error(f"[BINDER] Cannot rebind: instance {instance_id} not bound")
            return BindResponse(
                success=False,
                instance_id=instance_id,
                message="Instance not bound"
            )

        binding = self._bindings[instance_id]

        # Re-resolve all MCPs
        mcp_names = list(binding.mcps.keys())
        resolved, not_found = self.registry.resolve_names(mcp_names)

        # Update URLs and check health
        for name in mcp_names:
            if name in resolved:
                is_healthy = await self._check_mcp_health(name, resolved[name])
                if is_healthy:
                    binding.mcps[name].url = resolved[name]
                    binding.reactivate_mcp(name)
                else:
                    binding.suspend_mcp(name, "Health check failed during rebind")
            else:
                binding.suspend_mcp(name, "Not found in registry during rebind")

        binding.updated_at = datetime.utcnow()

        if self.db:
            await self._persist_binding(binding)

        logger.info(f"[BINDER] Rebound instance {instance_id}: active={binding.get_active_mcp_names()}")

        return BindResponse(
            success=True,
            instance_id=instance_id,
            bound_mcps=binding.get_active_mcp_names(),
            mcp_servers_config=binding.get_mcp_servers_config(),
        )

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_binding(self, instance_id: str) -> Optional[MCPBinding]:
        """Get binding for an instance."""
        return self._bindings.get(instance_id)

    def get_all_bindings(self) -> list[MCPBinding]:
        """Get all active bindings."""
        return list(self._bindings.values())

    def get_bindings_for_agent(self, agent_id: str) -> list[MCPBinding]:
        """Get all bindings for a specific agent type."""
        return [b for b in self._bindings.values() if b.agent_id == agent_id]

    def get_bindings_using_mcp(self, mcp_name: str) -> list[MCPBinding]:
        """Get all bindings that use a specific MCP."""
        return [b for b in self._bindings.values() if mcp_name in b.mcps]

    def get_mcp_servers_config(self, instance_id: str) -> Optional[dict]:
        """Get mcpServers config for an instance."""
        binding = self._bindings.get(instance_id)
        if binding:
            return binding.get_mcp_servers_config()
        return None

    def get_stats(self) -> dict:
        """Get binder statistics."""
        total_bindings = len(self._bindings)
        active_bindings = sum(1 for b in self._bindings.values() if b.status == BindingStatus.ACTIVE)

        mcp_usage = {}
        for binding in self._bindings.values():
            for mcp_name in binding.mcps.keys():
                mcp_usage[mcp_name] = mcp_usage.get(mcp_name, 0) + 1

        return {
            "total_bindings": total_bindings,
            "active_bindings": active_bindings,
            "mcp_usage": mcp_usage,
            "health_check_running": self._running,
        }

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    async def start_health_monitoring(self, interval_seconds: int = 60):
        """Start background health monitoring of bound MCPs."""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(
            self._health_monitor_loop(interval_seconds)
        )
        logger.info(f"[BINDER] Started health monitoring (interval={interval_seconds}s)")

    async def stop_health_monitoring(self):
        """Stop background health monitoring."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("[BINDER] Stopped health monitoring")

    async def _health_monitor_loop(self, interval: int):
        """Background loop that checks health of bound MCPs."""
        while self._running:
            try:
                await self._check_all_bindings_health()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BINDER] Health monitor error: {e}")
                await asyncio.sleep(interval)

    async def _check_all_bindings_health(self):
        """Check health of all MCPs in all bindings."""
        for binding in self._bindings.values():
            for mcp_name, entry in binding.mcps.items():
                if entry.status == BindingStatus.ACTIVE:
                    is_healthy = await self._check_mcp_health(mcp_name, entry.url)
                    if not is_healthy:
                        binding.suspend_mcp(mcp_name, "Health check failed")
                        logger.warning(f"[BINDER] Suspended MCP {mcp_name} for instance {binding.instance_id}")
                elif entry.status == BindingStatus.SUSPENDED:
                    # Try to recover
                    is_healthy = await self._check_mcp_health(mcp_name, entry.url)
                    if is_healthy:
                        binding.reactivate_mcp(mcp_name)
                        logger.info(f"[BINDER] Reactivated MCP {mcp_name} for instance {binding.instance_id}")

    async def _check_mcp_health(self, name: str, url: str, timeout: float = 3.0) -> bool:
        """Check if an MCP is healthy."""
        try:
            health_url = url.replace("/sse", "/health")
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(health_url)
                return response.status_code == 200
        except Exception:
            return False

    # =========================================================================
    # Agent Configuration
    # =========================================================================

    def _get_agent_mcp_configs(self, agent_id: str) -> list[str]:
        """Read mcp_configs from agent's definition.yaml."""
        try:
            definition_path = Path(self.agents_config_path) / agent_id / "definition.yaml"

            if not definition_path.exists():
                logger.warning(f"[BINDER] Agent definition not found: {definition_path}")
                return []

            with open(definition_path) as f:
                definition = yaml.safe_load(f)

            mcp_configs = definition.get("mcp_configs", [])
            logger.debug(f"[BINDER] Agent {agent_id} has mcp_configs: {mcp_configs}")
            return mcp_configs

        except Exception as e:
            logger.error(f"[BINDER] Error reading agent definition: {e}")
            return []

    def _get_policy(self, agent_id: str) -> BindingPolicy:
        """Get binding policy for an agent."""
        if agent_id in self._policies:
            return self._policies[agent_id]
        return self._default_policy

    def set_policy(self, agent_id: str, policy: BindingPolicy):
        """Set binding policy for an agent."""
        self._policies[agent_id] = policy
        logger.info(f"[BINDER] Set policy for {agent_id}: allowed={policy.allowed_mcps}, denied={policy.denied_mcps}")

    # =========================================================================
    # Persistence
    # =========================================================================

    async def _persist_binding(self, binding: MCPBinding):
        """Persist binding to MongoDB."""
        if not self.db:
            return

        try:
            collection = self.db["mcp_bindings"]
            doc = binding.model_dump()
            doc["_id"] = binding.instance_id

            await asyncio.to_thread(
                collection.update_one,
                {"_id": binding.instance_id},
                {"$set": doc},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"[BINDER] Failed to persist binding: {e}")

    async def load_active_bindings(self):
        """Load active bindings from MongoDB on startup."""
        if not self.db:
            return

        try:
            collection = self.db["mcp_bindings"]
            cursor = collection.find({"status": BindingStatus.ACTIVE.value})

            count = 0
            for doc in cursor:
                try:
                    binding = MCPBinding(**doc)
                    self._bindings[binding.instance_id] = binding
                    count += 1
                except Exception as e:
                    logger.warning(f"[BINDER] Failed to load binding: {e}")

            logger.info(f"[BINDER] Loaded {count} active bindings from database")

        except Exception as e:
            logger.warning(f"[BINDER] Failed to load bindings: {e}")


# Global binder instance
_binder: Optional[MCPBinder] = None


def get_mcp_binder() -> MCPBinder:
    """Get the global MCP Binder instance."""
    if _binder is None:
        raise RuntimeError("MCPBinder not initialized. Call init_mcp_binder first.")
    return _binder


def init_mcp_binder(
    registry_service: MCPRegistryService,
    db: Optional[Database] = None,
    agents_config_path: Optional[str] = None,
) -> MCPBinder:
    """Initialize the global MCP Binder."""
    global _binder
    _binder = MCPBinder(
        registry_service=registry_service,
        db=db,
        agents_config_path=agents_config_path,
    )
    return _binder
