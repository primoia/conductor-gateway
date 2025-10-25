"""
Agents Router - Proxy endpoints for listing available agents
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from src.clients.conductor_client import ConductorClient

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/api",
    tags=["agents"],
)


# Dependency to get conductor client
async def get_conductor_client():
    """Get conductor client instance"""
    from src.api.app import conductor_client
    if not conductor_client:
        raise HTTPException(status_code=503, detail="Conductor client not initialized")
    return conductor_client


@router.get("/agents")
async def list_agents(client: ConductorClient = Depends(get_conductor_client)):
    """
    List all available agents from conductor-api

    Returns list of agents with full metadata (name, emoji, description, etc.)
    """
    try:
        logger.info("Fetching agents from conductor-api")
        agents = await client.list_agents()
        logger.info(f"Retrieved {len(agents)} agents from conductor-api")
        return agents
    except Exception as e:
        logger.error(f"Error fetching agents: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch agents: {str(e)}"
        )
