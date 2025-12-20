"""
Pydantic models for MCP Registry API.

The MCP Registry manages both internal (gateway-hosted) and external (sidecar) MCP servers.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class MCPType(str, Enum):
    """Type of MCP server."""
    INTERNAL = "internal"  # Hosted inside gateway (prospector, database, conductor)
    EXTERNAL = "external"  # Sidecar containers that self-register


class MCPStatus(str, Enum):
    """Health status of an MCP server."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MCPMetadata(BaseModel):
    """Optional metadata for an MCP entry."""

    category: Optional[str] = Field(None, description="Category for grouping (e.g., verticals, billing)")
    description: Optional[str] = Field(None, description="Human-readable description")
    version: Optional[str] = Field(None, description="Version of the MCP/service")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")

    model_config = ConfigDict(extra="allow")  # Allow additional fields


class MCPRegisterRequest(BaseModel):
    """Request model for registering an external MCP server."""

    name: str = Field(..., min_length=1, max_length=100, description="Unique identifier for this MCP")
    url: str = Field(..., description="SSE endpoint URL (e.g., http://crm-mcp-sidecar:9201/sse)")
    backend_url: Optional[str] = Field(None, description="URL of the backend API this MCP proxies")
    metadata: Optional[MCPMetadata] = Field(None, description="Optional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "crm",
                "url": "http://crm-mcp-sidecar:9201/sse",
                "backend_url": "http://crm-backend:8001",
                "metadata": {
                    "category": "verticals",
                    "description": "CRM Lead Management API",
                    "version": "1.0.0"
                }
            }
        }
    )


class MCPHeartbeatRequest(BaseModel):
    """Request model for heartbeat updates."""

    tools_count: Optional[int] = Field(None, description="Number of tools currently exposed")
    status: Optional[MCPStatus] = Field(MCPStatus.HEALTHY, description="Current status")


class MCPRegistryEntry(BaseModel):
    """Full MCP registry entry stored in MongoDB."""

    id: Optional[str] = Field(None, alias="_id", description="MongoDB document ID")
    name: str = Field(..., description="Unique identifier")
    type: MCPType = Field(..., description="Internal or external MCP")
    url: str = Field(..., description="SSE endpoint URL")
    backend_url: Optional[str] = Field(None, description="Backend API URL (for external MCPs)")
    status: MCPStatus = Field(MCPStatus.UNKNOWN, description="Current health status")
    tools_count: int = Field(0, description="Number of exposed tools")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    registered_at: datetime = Field(default_factory=datetime.utcnow, description="Registration timestamp")
    metadata: MCPMetadata = Field(default_factory=MCPMetadata, description="Additional metadata")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "name": "crm",
                "type": "external",
                "url": "http://crm-mcp-sidecar:9201/sse",
                "backend_url": "http://crm-backend:8001",
                "status": "healthy",
                "tools_count": 43,
                "last_heartbeat": "2025-12-20T10:30:00Z",
                "registered_at": "2025-12-20T10:00:00Z",
                "metadata": {
                    "category": "verticals",
                    "description": "CRM Lead Management API"
                }
            }
        }
    )


class MCPRegistryEntryResponse(BaseModel):
    """Response model for a single MCP entry."""

    name: str
    type: MCPType
    url: str
    backend_url: Optional[str] = None
    status: MCPStatus
    tools_count: int = 0
    last_heartbeat: Optional[datetime] = None
    registered_at: Optional[datetime] = None
    metadata: Optional[MCPMetadata] = None

    model_config = ConfigDict(populate_by_name=True)


class MCPListResponse(BaseModel):
    """Response model for listing MCPs."""

    items: list[MCPRegistryEntryResponse] = Field(..., description="List of MCP entries")
    total: int = Field(..., description="Total count")
    internal_count: int = Field(..., description="Count of internal MCPs")
    external_count: int = Field(..., description="Count of external MCPs")
    healthy_count: int = Field(..., description="Count of healthy MCPs")


class MCPHealthResponse(BaseModel):
    """Response model for health check."""

    name: str
    status: MCPStatus
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    tools_count: Optional[int] = None
    last_heartbeat: Optional[datetime] = None
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class MCPResolveRequest(BaseModel):
    """Request model for resolving MCP names to URLs."""

    names: list[str] = Field(..., description="List of MCP names to resolve")


class MCPResolveResponse(BaseModel):
    """Response model for resolved MCP URLs."""

    resolved: dict[str, str] = Field(..., description="Map of name -> URL for found MCPs")
    not_found: list[str] = Field(default_factory=list, description="Names that could not be resolved")
