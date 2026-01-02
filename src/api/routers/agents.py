"""
Agents Router - Proxy endpoints for managing agents via conductor-api
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.clients.conductor_client import ConductorClient

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(
    prefix="/api",
    tags=["agents"],
)


# Request model for agent creation (normalized for web and terminal)
class AgentCreateRequest(BaseModel):
    """Request model for creating a new agent (normalized format)"""
    name: str = Field(..., description="Name of the agent (must end with _Agent)")
    description: str = Field(..., min_length=10, max_length=200, description="Description of the agent's purpose")
    persona_content: str = Field(..., min_length=50, description="Agent persona in Markdown (must start with #)")
    emoji: str = Field(default="🤖", description="Emoji for visual representation")
    tags: Optional[List[str]] = Field(default=None, description="Tags for search and organization")
    mcp_configs: Optional[List[str]] = Field(default=None, description="List of MCP sidecar names to bind")


# Request model for agent update
class AgentUpdateRequest(BaseModel):
    """Request model for updating an existing agent"""
    mcp_configs: Optional[List[str]] = Field(default=None, description="List of MCP sidecar names to bind")
    # Future: add more editable fields as needed
    # description: Optional[str] = None
    # emoji: Optional[str] = None
    # tags: Optional[List[str]] = None


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


@router.post("/agents")
async def create_agent(
    request: AgentCreateRequest,
    client: ConductorClient = Depends(get_conductor_client)
):
    """
    Create a new agent via conductor-api (normalized format)

    Creates the agent definition and persona in the storage backend.
    The agent will be available for instantiation after creation.

    **Request Body:**
    - `name`: Name of the agent (must end with _Agent)
    - `description`: Description of the agent's purpose (10-200 chars)
    - `persona_content`: Agent persona in Markdown (min 50 chars, must start with #)
    - `emoji`: Emoji for visual representation (default: 🤖)
    - `tags`: Tags for search and organization (optional)
    - `mcp_configs`: List of MCP sidecar names to bind (optional)

    **Returns:**
    - `status`: "success" or "error"
    - `agent_id`: The generated agent ID
    - `message`: Human-readable message
    """
    try:
        logger.info(f"🛠️ Creating new agent: {request.name}")
        logger.info(f"   - description: {request.description[:50]}...")
        logger.info(f"   - emoji: {request.emoji}")
        logger.info(f"   - tags: {request.tags}")
        logger.info(f"   - mcp_configs: {request.mcp_configs}")
        logger.info(f"   - persona_content: {request.persona_content[:50]}...")

        result = await client.create_agent(
            name=request.name,
            description=request.description,
            persona_content=request.persona_content,
            emoji=request.emoji,
            tags=request.tags,
            mcp_configs=request.mcp_configs,
        )

        logger.info(f"✅ Agent created successfully: {result.get('agent_id')}")
        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error creating agent: {error_msg}")

        # Check for specific error types
        if "409" in error_msg or "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"Agent already exists: {request.name}"
            )

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create agent: {error_msg}"
        )


@router.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    request: AgentUpdateRequest
):
    """
    Update an existing agent's configuration.

    Currently supports updating:
    - `mcp_configs`: List of MCP sidecar names to bind

    **Path Parameters:**
    - `agent_id`: The agent ID (e.g., "MyAgent_Agent")

    **Request Body:**
    - `mcp_configs`: List of MCP sidecar names (optional)

    **Returns:**
    - `success`: boolean
    - `agent`: Updated agent object
    - `message`: Human-readable message
    """
    try:
        from src.api.app import mongo_db
        from datetime import datetime, timezone

        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        logger.info(f"📝 Updating agent: {agent_id}")
        logger.info(f"   - mcp_configs: {request.mcp_configs}")

        agents_collection = mongo_db["agents"]

        # Find the agent
        agent = agents_collection.find_one({"agent_id": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        # Build update document
        update_fields = {"updated_at": datetime.now(timezone.utc)}

        if request.mcp_configs is not None:
            # Update mcp_configs in definition if exists, otherwise at root level
            if "definition" in agent:
                update_fields["definition.mcp_configs"] = request.mcp_configs
            else:
                update_fields["mcp_configs"] = request.mcp_configs

        # Perform update
        result = agents_collection.update_one(
            {"agent_id": agent_id},
            {"$set": update_fields}
        )

        if result.modified_count == 0 and result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        # Fetch updated agent
        updated_agent = agents_collection.find_one({"agent_id": agent_id})

        # Build response
        if "definition" in updated_agent:
            definition = updated_agent.get("definition", {})
            agent_response = {
                "id": str(updated_agent.get("_id", "")),
                "agent_id": agent_id,
                "name": definition.get("name", ""),
                "emoji": definition.get("emoji", "🤖"),
                "description": definition.get("description", ""),
                "mcp_configs": definition.get("mcp_configs", []),
                "tags": definition.get("tags", [])
            }
        else:
            agent_response = {
                "id": str(updated_agent.get("_id", "")),
                "agent_id": agent_id,
                "name": updated_agent.get("name", ""),
                "emoji": updated_agent.get("emoji", "🤖"),
                "description": updated_agent.get("description", ""),
                "mcp_configs": updated_agent.get("mcp_configs", []),
                "tags": updated_agent.get("tags", [])
            }

        logger.info(f"✅ Agent updated successfully: {agent_id}")

        return {
            "success": True,
            "agent": agent_response,
            "message": f"Agent '{agent_id}' updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error updating agent: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update agent: {error_msg}"
        )


@router.get("/system/mcp/sidecars")
async def list_mcp_sidecars(client: ConductorClient = Depends(get_conductor_client)):
    """
    List all discovered MCP sidecars from the Docker network.

    Returns MCP sidecars that are running and available for agent binding.

    **Returns:**
    - `count`: Number of sidecars discovered
    - `sidecars`: List of sidecar objects with name, url, port, container_id
    """
    try:
        logger.info("🔍 Fetching MCP sidecars from conductor-api")
        result = await client.list_mcp_sidecars()
        logger.info(f"✅ Found {result.get('count', 0)} MCP sidecars")
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching MCP sidecars: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch MCP sidecars: {str(e)}"
        )
