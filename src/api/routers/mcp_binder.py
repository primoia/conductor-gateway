"""
MCP Binder API Routes.

Provides endpoints for:
- Binding/unbinding MCPs to agent instances
- Adding/removing MCPs dynamically
- Querying active bindings
- Managing binding policies
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.mcp_binder import get_mcp_binder, MCPBinder
from src.models.mcp_binder import (
    BindRequest,
    BindResponse,
    UnbindRequest,
    AddMCPRequest,
    RemoveMCPRequest,
    MCPBinding,
    BindingListResponse,
    BindingPolicy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/binder", tags=["MCP Binder"])


def get_binder() -> MCPBinder:
    """Dependency to get the MCP Binder."""
    try:
        return get_mcp_binder()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="MCP Binder not initialized")


# ============================================================================
# Bind/Unbind Operations
# ============================================================================

@router.post(
    "/bind",
    response_model=BindResponse,
    summary="Bind MCPs to an agent instance",
    description="Resolve and bind MCPs before an agent starts execution."
)
async def bind_mcps(
    request: BindRequest,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Bind MCPs to an agent instance.

    This is typically called before an agent starts execution.
    The binder will:
    1. Read mcp_configs from the agent's definition.yaml (or use provided list)
    2. Resolve MCP names to URLs via the Registry
    3. Health check each MCP
    4. Create the binding and return mcpServers config

    The returned mcp_servers_config can be passed directly to MCPClient.
    """
    try:
        response = await binder.bind(request)
        logger.info(f"Bound MCPs for instance {request.instance_id}: {response.bound_mcps}")
        return response
    except Exception as e:
        logger.error(f"Failed to bind MCPs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/unbind",
    status_code=204,
    summary="Unbind MCPs from an agent instance",
    description="Remove all MCP bindings when an agent finishes."
)
async def unbind_mcps(
    request: UnbindRequest,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Unbind all MCPs from an agent instance.

    This is typically called when an agent finishes execution.
    """
    success = await binder.unbind(request.instance_id, request.reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"Binding not found for instance {request.instance_id}")


@router.post(
    "/rebind/{instance_id}",
    response_model=BindResponse,
    summary="Rebind MCPs for an instance",
    description="Re-resolve and reconnect MCPs (e.g., after MCP recovery)."
)
async def rebind_mcps(
    instance_id: str,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Rebind MCPs for an agent instance.

    This re-resolves URLs and checks health, useful after MCP recovery.
    """
    response = await binder.rebind(instance_id)
    if not response.success:
        raise HTTPException(status_code=404, detail=response.message)
    return response


# ============================================================================
# Dynamic MCP Operations
# ============================================================================

@router.post(
    "/add-mcp",
    status_code=204,
    summary="Add MCP to running instance",
    description="Dynamically add an MCP to a running agent instance."
)
async def add_mcp_to_instance(
    request: AddMCPRequest,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Add an MCP to a running agent instance.

    This allows dynamic expansion of an agent's capabilities during execution.
    """
    success = await binder.add_mcp(request.instance_id, request.mcp_name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add MCP {request.mcp_name} to instance {request.instance_id}"
        )


@router.post(
    "/remove-mcp",
    status_code=204,
    summary="Remove MCP from running instance",
    description="Dynamically remove an MCP from a running agent instance."
)
async def remove_mcp_from_instance(
    request: RemoveMCPRequest,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Remove an MCP from a running agent instance.

    This allows dynamic restriction of an agent's capabilities during execution.
    """
    success = await binder.remove_mcp(request.instance_id, request.mcp_name, request.reason)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to remove MCP {request.mcp_name} from instance {request.instance_id}"
        )


# ============================================================================
# Query Operations
# ============================================================================

@router.get(
    "/bindings",
    response_model=BindingListResponse,
    summary="List all active bindings",
    description="Get a list of all currently active agent-MCP bindings."
)
async def list_bindings(
    agent_id: Optional[str] = Query(None, description="Filter by agent type"),
    mcp_name: Optional[str] = Query(None, description="Filter by MCP name"),
    binder: MCPBinder = Depends(get_binder)
):
    """
    List all active bindings.

    Can be filtered by agent type or MCP name.
    """
    if agent_id:
        bindings = binder.get_bindings_for_agent(agent_id)
    elif mcp_name:
        bindings = binder.get_bindings_using_mcp(mcp_name)
    else:
        bindings = binder.get_all_bindings()

    active_count = sum(1 for b in bindings if b.status.value == "active")

    return BindingListResponse(
        bindings=bindings,
        total=len(bindings),
        active_count=active_count
    )


@router.get(
    "/bindings/{instance_id}",
    response_model=MCPBinding,
    summary="Get binding details",
    description="Get details of a specific agent instance's bindings."
)
async def get_binding(
    instance_id: str,
    binder: MCPBinder = Depends(get_binder)
):
    """Get binding details for a specific instance."""
    binding = binder.get_binding(instance_id)
    if not binding:
        raise HTTPException(status_code=404, detail=f"Binding not found for instance {instance_id}")
    return binding


@router.get(
    "/bindings/{instance_id}/config",
    summary="Get mcpServers config for instance",
    description="Get the mcpServers configuration for use with MCPClient."
)
async def get_binding_config(
    instance_id: str,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Get mcpServers config for an instance.

    Returns the configuration dict that can be passed directly to MCPClient.from_dict().
    """
    config = binder.get_mcp_servers_config(instance_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Binding not found for instance {instance_id}")
    return config


@router.get(
    "/stats",
    summary="Get binder statistics",
    description="Get statistics about the MCP Binder."
)
async def get_binder_stats(
    binder: MCPBinder = Depends(get_binder)
):
    """Get binder statistics."""
    return binder.get_stats()


# ============================================================================
# Policy Management
# ============================================================================

@router.post(
    "/policies",
    status_code=201,
    summary="Set binding policy for an agent",
    description="Define what MCPs an agent is allowed to use."
)
async def set_policy(
    policy: BindingPolicy,
    binder: MCPBinder = Depends(get_binder)
):
    """
    Set a binding policy for an agent type.

    Policies define:
    - allowed_mcps: List of MCP names the agent can use (* = all)
    - denied_mcps: List of explicitly denied MCPs
    - max_concurrent_mcps: Maximum MCPs that can be bound at once
    - require_healthy: Whether to require health check before binding
    """
    binder.set_policy(policy.agent_id, policy)
    return {"success": True, "agent_id": policy.agent_id}


# ============================================================================
# Health Monitoring
# ============================================================================

@router.post(
    "/health-monitoring/start",
    summary="Start health monitoring",
    description="Start background health monitoring of bound MCPs."
)
async def start_health_monitoring(
    interval_seconds: int = Query(60, description="Health check interval in seconds"),
    binder: MCPBinder = Depends(get_binder)
):
    """Start background health monitoring."""
    await binder.start_health_monitoring(interval_seconds)
    return {"success": True, "interval_seconds": interval_seconds}


@router.post(
    "/health-monitoring/stop",
    summary="Stop health monitoring",
    description="Stop background health monitoring."
)
async def stop_health_monitoring(
    binder: MCPBinder = Depends(get_binder)
):
    """Stop background health monitoring."""
    await binder.stop_health_monitoring()
    return {"success": True}
