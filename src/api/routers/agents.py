"""
Agents Router - Proxy endpoints for managing agents via conductor-api
"""

import logging
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from src.clients.conductor_client import ConductorClient

logger = logging.getLogger(__name__)

# Knowledge Hub configuration (primary source for agent suggestions)
KNOWLEDGE_HUB_URL = os.getenv("KNOWLEDGE_HUB_URL", "http://primoia-shared-knowledge-hub-api:8000")
KNOWLEDGE_HUB_TIMEOUT = float(os.getenv("KNOWLEDGE_HUB_TIMEOUT", "10.0"))

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
    List all available agents from MongoDB (primary) with fallback to conductor-api.

    Returns list of agents with full metadata (name, emoji, description, mcp_configs, etc.)
    """
    try:
        from src.api.app import mongo_db

        # Try MongoDB first (has the most up-to-date data including mcp_configs)
        if mongo_db is not None:
            logger.info("Fetching agents from MongoDB")
            agents_collection = mongo_db["agents"]
            agents_cursor = agents_collection.find({})
            agents_list = list(agents_cursor)

            if agents_list:
                # Transform MongoDB documents to API format
                result = []
                for agent in agents_list:
                    # Check if agent uses 'definition' structure
                    if "definition" in agent:
                        definition = agent.get("definition", {})
                        agent_data = {
                            "id": agent.get("agent_id", str(agent.get("_id", ""))),
                            "name": definition.get("name", ""),
                            "emoji": definition.get("emoji", "🤖"),
                            "description": definition.get("description", ""),
                            "prompt": definition.get("prompt", ""),
                            "model": definition.get("model", ""),
                            "is_councilor": agent.get("is_councilor", False),
                            "mcp_configs": definition.get("mcp_configs", []),
                            "created_at": agent.get("created_at"),
                            "group": definition.get("group", "other"),
                            "tags": definition.get("tags", [])
                        }
                    else:
                        # Flat structure
                        agent_data = {
                            "id": agent.get("agent_id", str(agent.get("_id", ""))),
                            "name": agent.get("name", ""),
                            "emoji": agent.get("emoji", "🤖"),
                            "description": agent.get("description", ""),
                            "prompt": agent.get("prompt", ""),
                            "model": agent.get("model", ""),
                            "is_councilor": agent.get("is_councilor", False),
                            "mcp_configs": agent.get("mcp_configs", []),
                            "created_at": agent.get("created_at"),
                            "group": agent.get("group", "other"),
                            "tags": agent.get("tags", [])
                        }
                    result.append(agent_data)

                logger.info(f"Retrieved {len(result)} agents from MongoDB")
                return result

        # Fallback to Conductor API if MongoDB is empty or unavailable
        logger.info("Fetching agents from conductor-api (fallback)")
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


class AgentFullUpdateRequest(BaseModel):
    """Request model for full agent update (PUT)"""
    name: Optional[str] = Field(default=None, description="Name of the agent")
    description: Optional[str] = Field(default=None, description="Description of the agent's purpose")
    group: Optional[str] = Field(default=None, description="Agent group/category")
    emoji: Optional[str] = Field(default=None, description="Emoji for visual representation")
    tags: Optional[List[str]] = Field(default=None, description="Tags for search and organization")
    persona_content: Optional[str] = Field(default=None, description="Agent persona in Markdown")
    mcp_configs: Optional[List[str]] = Field(default=None, description="List of MCP sidecar names to bind")


@router.put("/agents/{agent_id}")
async def update_agent_full(
    agent_id: str,
    request: AgentFullUpdateRequest
):
    """
    Full update of an existing agent's configuration.

    **Path Parameters:**
    - `agent_id`: The agent ID (e.g., "MyAgent_Agent")

    **Request Body:**
    - `name`: Name of the agent (optional)
    - `description`: Description of the agent's purpose (optional)
    - `group`: Agent group/category (optional)
    - `emoji`: Emoji for visual representation (optional)
    - `tags`: Tags for search and organization (optional)
    - `persona_content`: Agent persona in Markdown (optional)
    - `mcp_configs`: List of MCP sidecar names to bind (optional)

    **Returns:**
    - `status`: "success" or "error"
    - `agent_id`: The agent ID
    - `updated_fields`: List of fields that were updated
    """
    try:
        from src.api.app import mongo_db
        from datetime import datetime, timezone

        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        logger.info(f"📝 [PUT] Full update for agent: {agent_id}")
        logger.info(f"   - Request: {request}")

        agents_collection = mongo_db["agents"]

        # Find the agent
        agent = agents_collection.find_one({"agent_id": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        # Build update document
        update_fields = {"updated_at": datetime.now(timezone.utc)}
        updated_field_names = []

        # Check if agent uses 'definition' structure or flat structure
        has_definition = "definition" in agent

        # Update name
        if request.name is not None:
            if has_definition:
                update_fields["definition.name"] = request.name
            else:
                update_fields["name"] = request.name
            updated_field_names.append("name")

        # Update description
        if request.description is not None:
            if has_definition:
                update_fields["definition.description"] = request.description
            else:
                update_fields["description"] = request.description
            updated_field_names.append("description")

        # Update group
        if request.group is not None:
            if has_definition:
                update_fields["definition.group"] = request.group
            else:
                update_fields["group"] = request.group
            updated_field_names.append("group")

        # Update emoji
        if request.emoji is not None:
            if has_definition:
                update_fields["definition.emoji"] = request.emoji
            else:
                update_fields["emoji"] = request.emoji
            updated_field_names.append("emoji")

        # Update tags
        if request.tags is not None:
            if has_definition:
                update_fields["definition.tags"] = request.tags
            else:
                update_fields["tags"] = request.tags
            updated_field_names.append("tags")

        # Update mcp_configs
        if request.mcp_configs is not None:
            if has_definition:
                update_fields["definition.mcp_configs"] = request.mcp_configs
            else:
                update_fields["mcp_configs"] = request.mcp_configs
            updated_field_names.append("mcp_configs")

        # Update persona_content - stored in persona.content
        if request.persona_content is not None:
            update_fields["persona.content"] = request.persona_content
            update_fields["persona.updated_at"] = datetime.now(timezone.utc).isoformat()
            updated_field_names.append("persona_content")

        if not updated_field_names:
            return {
                "status": "success",
                "agent_id": agent_id,
                "updated_fields": [],
                "message": "No fields to update"
            }

        # Perform update
        result = agents_collection.update_one(
            {"agent_id": agent_id},
            {"$set": update_fields}
        )

        logger.info(f"✅ [PUT] Agent updated: {agent_id}, fields: {updated_field_names}")

        return {
            "status": "success",
            "agent_id": agent_id,
            "updated_fields": updated_field_names,
            "message": f"Agent '{agent_id}' updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ [PUT] Error updating agent: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update agent: {error_msg}"
        )


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """
    Delete an agent from the system.

    **Path Parameters:**
    - `agent_id`: The agent ID (e.g., "MyAgent_Agent")

    **Returns:**
    - `success`: boolean
    - `agent_id`: The deleted agent ID
    - `message`: Human-readable message
    """
    try:
        from src.api.app import mongo_db

        if mongo_db is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        logger.info(f"🗑️ Deleting agent: {agent_id}")

        agents_collection = mongo_db["agents"]

        # Find the agent first to confirm it exists
        agent = agents_collection.find_one({"agent_id": agent_id})
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        # Delete the agent
        result = agents_collection.delete_one({"agent_id": agent_id})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Failed to delete agent: {agent_id}")

        logger.info(f"✅ Agent deleted successfully: {agent_id}")

        return {
            "success": True,
            "agent_id": agent_id,
            "message": f"Agent '{agent_id}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error deleting agent: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete agent: {error_msg}"
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


# ============================================================================
# AGENT SUGGESTION (Qdrant-based semantic agent matching)
# ============================================================================

class AgentSuggestRequest(BaseModel):
    """Request model for agent suggestion"""
    message: str = Field(..., min_length=1, description="User message to analyze")
    current_agent_id: Optional[str] = Field(default=None, description="Currently selected agent ID")


class AgentSuggestion(BaseModel):
    """Single agent suggestion"""
    agent_id: str
    name: str
    emoji: str
    description: str
    score: float
    reason: str


class AgentSuggestResponse(BaseModel):
    """Response model for agent suggestion"""
    suggested: Optional[AgentSuggestion] = None
    alternatives: List[AgentSuggestion] = []
    current_is_best: bool = True
    message: str
    source: str = "knowledge-hub"


async def _suggest_via_knowledge_hub(message: str, current_agent_id: Optional[str]) -> Optional[AgentSuggestResponse]:
    """
    Try to get agent suggestion from Knowledge Hub API.
    Returns None if Knowledge Hub is unavailable or returns an error.
    """
    try:
        async with httpx.AsyncClient(timeout=KNOWLEDGE_HUB_TIMEOUT) as client:
            response = await client.post(
                f"{KNOWLEDGE_HUB_URL}/api/v1/suggest-agent",
                json={
                    "message": message,
                    "current_agent_id": current_agent_id,
                }
            )
            response.raise_for_status()
            data = response.json()

            # Parse response into our models
            suggested = None
            if data.get("suggested"):
                s = data["suggested"]
                suggested = AgentSuggestion(
                    agent_id=s["agent_id"],
                    name=s["name"],
                    emoji=s.get("emoji", "🤖"),
                    description=s.get("description", ""),
                    score=s["score"],
                    reason=s["reason"],
                )

            alternatives = [
                AgentSuggestion(
                    agent_id=a["agent_id"],
                    name=a["name"],
                    emoji=a.get("emoji", "🤖"),
                    description=a.get("description", ""),
                    score=a["score"],
                    reason=a["reason"],
                )
                for a in data.get("alternatives", [])
            ]

            return AgentSuggestResponse(
                suggested=suggested,
                alternatives=alternatives,
                current_is_best=data.get("current_is_best", True),
                message=data.get("message", ""),
                source="knowledge-hub",
            )

    except httpx.TimeoutException:
        logger.warning(f"⚠️ [SUGGEST] Knowledge Hub timeout after {KNOWLEDGE_HUB_TIMEOUT}s")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"⚠️ [SUGGEST] Knowledge Hub HTTP error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ [SUGGEST] Knowledge Hub error: {e}")
        return None


@router.post("/agents/suggest")
async def suggest_agent(request: AgentSuggestRequest):
    """
    Suggest the best agent for a given message using semantic search via Knowledge Hub.

    **Request Body:**
    - `message`: The user's message to analyze
    - `current_agent_id`: Currently selected agent (optional)

    **Returns:**
    - `suggested`: Best matching agent (if different from current)
    - `alternatives`: Other good matches
    - `current_is_best`: True if current agent is the best match
    - `message`: Human-readable explanation
    - `source`: "knowledge-hub" or "fallback"
    """
    try:
        logger.info(f"🧠 [SUGGEST] Analyzing message: {request.message[:50]}...")

        result = await _suggest_via_knowledge_hub(
            request.message,
            request.current_agent_id
        )
        if result:
            logger.info(f"🧠 [SUGGEST] Using Knowledge Hub response")
            return result

        logger.warning("⚠️ [SUGGEST] Knowledge Hub unavailable")
        return AgentSuggestResponse(
            suggested=None,
            alternatives=[],
            current_is_best=True,
            message="Knowledge Hub indisponível. Tente novamente mais tarde.",
            source="fallback"
        )

    except Exception as e:
        logger.error(f"❌ [SUGGEST] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error suggesting agent: {str(e)}")
