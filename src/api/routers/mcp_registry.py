"""
MCP Registry API Routes.

Provides endpoints for:
- Registering/unregistering external MCP servers (sidecars)
- Listing all available MCPs (internal + external)
- Health checking MCPs
- Resolving MCP names to URLs
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from src.models.mcp_registry import (
    MCPType,
    MCPStatus,
    MCPRegisterRequest,
    MCPHeartbeatRequest,
    MCPRegistryEntry,
    MCPRegistryEntryResponse,
    MCPListResponse,
    MCPHealthResponse,
    MCPResolveRequest,
    MCPResolveResponse,
    MCPConfigResponse,
)
from src.services.mcp_registry_service import MCPRegistryService
from src.services.mcp_mesh_service import mesh_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP Registry"])

# Service instance - will be initialized via dependency
_registry_service: Optional[MCPRegistryService] = None


def init_mcp_registry_service(db: Database):
    """Initialize the MCP Registry service with database connection."""
    global _registry_service
    _registry_service = MCPRegistryService(db)
    logger.info("MCP Registry service initialized")


def get_registry_service() -> MCPRegistryService:
    """Dependency to get the registry service."""
    if _registry_service is None:
        raise HTTPException(status_code=503, detail="MCP Registry service not initialized")
    return _registry_service


# ============================================================================
# Registration Endpoints
# ============================================================================

@router.post(
    "/register",
    response_model=MCPRegistryEntry,
    status_code=201,
    summary="Register an external MCP server",
    description="Register a new MCP sidecar. Called by sidecars on startup."
)
async def register_mcp(
    request: MCPRegisterRequest,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Register an external MCP server (sidecar).

    This endpoint is called by MCP sidecars when they start up.
    If an MCP with the same name already exists, it will be updated (re-registration).

    Internal MCPs (prospector, database, conductor) cannot be overwritten.
    """
    try:
        entry = service.register(request)
        logger.info(f"MCP registered: {request.name} at {request.url}")
        return entry
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to register MCP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register MCP")


@router.delete(
    "/unregister/{name}",
    status_code=204,
    summary="Unregister an MCP server",
    description="Remove an external MCP from the registry. Called by sidecars on shutdown."
)
async def unregister_mcp(
    name: str,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Unregister an external MCP server.

    This endpoint is called by MCP sidecars when they shut down gracefully.
    Internal MCPs cannot be unregistered.
    """
    try:
        success = service.unregister(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"MCP '{name}' not found")
        logger.info(f"MCP unregistered: {name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unregister MCP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to unregister MCP")


@router.post(
    "/heartbeat/{name}",
    status_code=204,
    summary="Send heartbeat for an MCP",
    description="Update heartbeat timestamp. Called periodically by sidecars."
)
async def heartbeat(
    name: str,
    request: Optional[MCPHeartbeatRequest] = None,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Update heartbeat for an MCP server.

    Sidecars should call this every 30 seconds to indicate they're alive.
    MCPs that don't send heartbeats for 90 seconds are marked unhealthy.
    """
    tools_count = request.tools_count if request else None
    success = service.heartbeat(name, tools_count)

    if not success:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not found")


# ============================================================================
# Query Endpoints
# ============================================================================

@router.get(
    "/list",
    response_model=MCPListResponse,
    summary="List all registered MCPs",
    description="Get a list of all MCPs (internal and external) with optional filters."
)
async def list_mcps(
    type: Optional[MCPType] = Query(None, description="Filter by type (internal/external)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[MCPStatus] = Query(None, description="Filter by status"),
    healthy_only: bool = Query(False, description="Only return healthy MCPs"),
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    List all registered MCP servers.

    Returns both internal MCPs (hosted in gateway) and external MCPs (sidecars).
    Supports filtering by type, category, and status.
    """
    items = service.list_all(
        type_filter=type,
        category_filter=category,
        status_filter=status,
        healthy_only=healthy_only
    )

    stats = service.get_stats()

    return MCPListResponse(
        items=items,
        total=len(items),
        internal_count=stats["internal"],
        external_count=stats["external"],
        healthy_count=stats["healthy"]
    )


@router.get(
    "/mesh",
    summary="Get Active MCP Mesh Topology",
    description="Returns the live, actively verified dynamic Service Mesh of MCP sidecars.",
)
async def get_mcp_mesh():
    """
    Get the current topology of the active MCP Service Mesh.
    This bypasses passive heartbeat registries and relies on the active background scanner.
    """
    return {
        "mesh_nodes": mesh_service.get_mesh_topology_as_dict(),
        "total_active": len(mesh_service.get_mesh_topology())
    }


@router.get(
    "/config",
    response_model=MCPConfigResponse,
    summary="Get MCP config for Claude CLI",
    description="Get mcpServers config ready for Claude CLI from agent/instance MCPs."
)
async def get_mcp_config(
    instance_id: Optional[str] = Query(None, description="Agent instance ID"),
    agent_id: Optional[str] = Query(None, description="Agent template ID"),
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Get MCP configuration in Claude CLI format.

    Combines MCPs from:
    1. Agent template (definition.mcp_configs)
    2. Instance extras (instance.mcp_configs)

    Returns mcpServers dict ready for Claude CLI --mcp-config.

    Example response:
    {
        "mcpServers": {
            "crm": {"type": "sse", "url": "http://localhost:13145/sse?auth=..."},
            "prospector": {"type": "sse", "url": "http://localhost:5007/sse"}
        }
    }
    """
    if not instance_id and not agent_id:
        raise HTTPException(
            status_code=400,
            detail="Either instance_id or agent_id must be provided"
        )

    config = service.get_mcp_config(instance_id=instance_id, agent_id=agent_id)
    logger.info(f"MCP config requested: instance={instance_id}, agent={agent_id}, mcps={list(config.mcpServers.keys())}")
    return config


@router.get(
    "/{name}",
    response_model=MCPRegistryEntryResponse,
    summary="Get MCP details",
    description="Get details of a specific MCP by name."
)
async def get_mcp(
    name: str,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Get details of a specific MCP.

    Returns the full registration entry including URL, status, and metadata.
    """
    entry = service.get_by_name(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"MCP '{name}' not found")
    return entry


@router.get(
    "/{name}/health",
    response_model=MCPHealthResponse,
    summary="Check MCP health",
    description="Actively check the health of an MCP server."
)
async def check_mcp_health(
    name: str,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Actively check health of an MCP server.

    Makes an HTTP request to the MCP's health endpoint and returns status with latency.
    """
    return await service.check_health(name)


# ============================================================================
# Resolution Endpoints
# ============================================================================

@router.post(
    "/resolve",
    response_model=MCPResolveResponse,
    summary="Resolve MCP names to URLs",
    description="Convert a list of MCP names to their SSE endpoint URLs."
)
async def resolve_mcps(
    request: MCPResolveRequest,
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Resolve MCP names to URLs.

    Used by the Conductor to convert mcp_configs (list of names) to actual URLs.
    Returns both resolved URLs and any names that couldn't be found.
    """
    resolved, not_found = service.resolve_names(request.names)

    if not_found:
        logger.warning(f"Could not resolve MCPs: {not_found}")

    return MCPResolveResponse(
        resolved=resolved,
        not_found=not_found
    )


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.get(
    "/stats",
    summary="Get registry statistics",
    description="Get counts and statistics about registered MCPs."
)
async def get_stats(
    service: MCPRegistryService = Depends(get_registry_service)
):
    """Get statistics about the MCP registry."""
    return service.get_stats()


@router.post(
    "/cleanup",
    summary="Cleanup stale entries",
    description="Remove external MCPs that haven't sent heartbeat in a long time."
)
async def cleanup_stale(
    max_age_hours: int = Query(24, description="Max hours since last heartbeat"),
    service: MCPRegistryService = Depends(get_registry_service)
):
    """
    Cleanup stale MCP entries.

    Removes external MCPs that haven't sent a heartbeat in the specified time.
    Internal MCPs are never removed.
    """
    count = service.cleanup_stale_entries(max_age_hours)
    return {"removed": count}
