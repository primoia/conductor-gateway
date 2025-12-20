"""
Models for MCP Binder - the core component that manages agent-MCP bindings.

The Binder is responsible for:
- Binding MCPs to agent instances at runtime
- Unbinding when agents finish
- Dynamic add/remove of MCPs during execution
- Health monitoring of bound MCPs
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BindingStatus(str, Enum):
    """Status of an MCP binding."""
    ACTIVE = "active"           # Binding is active and healthy
    SUSPENDED = "suspended"     # Temporarily suspended (MCP unhealthy)
    ERROR = "error"            # Binding failed
    UNBOUND = "unbound"        # Explicitly unbound


class MCPBindingEntry(BaseModel):
    """A single MCP in a binding."""

    name: str = Field(..., description="MCP name (e.g., 'prospector')")
    url: str = Field(..., description="Resolved SSE URL")
    status: BindingStatus = Field(BindingStatus.ACTIVE)
    bound_at: datetime = Field(default_factory=datetime.utcnow)
    last_health_check: Optional[datetime] = None
    error_message: Optional[str] = None


class MCPBinding(BaseModel):
    """
    Represents a binding between an agent instance and its MCPs.

    Each running agent instance has one MCPBinding that tracks
    which MCPs it can use and their current status.
    """

    instance_id: str = Field(..., description="Agent instance ID")
    agent_id: str = Field(..., description="Agent template ID (e.g., 'Hunter_Agent')")
    conversation_id: Optional[str] = Field(None, description="Conversation context")
    screenplay_id: Optional[str] = Field(None, description="Screenplay context")

    mcps: dict[str, MCPBindingEntry] = Field(
        default_factory=dict,
        description="Map of MCP name -> binding entry"
    )

    status: BindingStatus = Field(BindingStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Metrics
    total_tool_calls: int = Field(0, description="Total tool calls made via bound MCPs")

    def get_mcp_servers_config(self) -> dict:
        """
        Generate mcpServers config for MCPClient.

        Returns:
            Dict in format {"mcpServers": {"name": {"url": "...", "transport": "sse"}}}
        """
        mcp_servers = {}
        for name, entry in self.mcps.items():
            if entry.status == BindingStatus.ACTIVE:
                mcp_servers[name] = {
                    "url": entry.url,
                    "transport": "sse"
                }
        return {"mcpServers": mcp_servers}

    def get_active_mcp_names(self) -> list[str]:
        """Get list of active MCP names."""
        return [
            name for name, entry in self.mcps.items()
            if entry.status == BindingStatus.ACTIVE
        ]

    def add_mcp(self, name: str, url: str) -> bool:
        """Add an MCP to this binding."""
        if name in self.mcps:
            return False

        self.mcps[name] = MCPBindingEntry(name=name, url=url)
        self.updated_at = datetime.utcnow()
        return True

    def remove_mcp(self, name: str) -> bool:
        """Remove an MCP from this binding."""
        if name not in self.mcps:
            return False

        del self.mcps[name]
        self.updated_at = datetime.utcnow()
        return True

    def suspend_mcp(self, name: str, reason: str = None) -> bool:
        """Suspend an MCP (e.g., due to health check failure)."""
        if name not in self.mcps:
            return False

        self.mcps[name].status = BindingStatus.SUSPENDED
        self.mcps[name].error_message = reason
        self.updated_at = datetime.utcnow()
        return True

    def reactivate_mcp(self, name: str) -> bool:
        """Reactivate a suspended MCP."""
        if name not in self.mcps:
            return False

        self.mcps[name].status = BindingStatus.ACTIVE
        self.mcps[name].error_message = None
        self.mcps[name].last_health_check = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        return True


class BindRequest(BaseModel):
    """Request to bind MCPs to an agent instance."""

    instance_id: str = Field(..., description="Agent instance ID")
    agent_id: str = Field(..., description="Agent template ID")
    mcp_names: Optional[list[str]] = Field(
        None,
        description="Explicit MCP names to bind (overrides definition.yaml)"
    )
    conversation_id: Optional[str] = None
    screenplay_id: Optional[str] = None


class BindResponse(BaseModel):
    """Response from bind operation."""

    success: bool
    instance_id: str
    bound_mcps: list[str] = Field(default_factory=list)
    failed_mcps: list[str] = Field(default_factory=list)
    mcp_servers_config: dict = Field(default_factory=dict)
    message: Optional[str] = None


class UnbindRequest(BaseModel):
    """Request to unbind MCPs from an agent instance."""

    instance_id: str = Field(..., description="Agent instance ID")
    reason: Optional[str] = Field(None, description="Reason for unbinding")


class AddMCPRequest(BaseModel):
    """Request to add an MCP to a running agent instance."""

    instance_id: str
    mcp_name: str


class RemoveMCPRequest(BaseModel):
    """Request to remove an MCP from a running agent instance."""

    instance_id: str
    mcp_name: str
    reason: Optional[str] = None


class BindingListResponse(BaseModel):
    """Response listing all active bindings."""

    bindings: list[MCPBinding] = Field(default_factory=list)
    total: int = 0
    active_count: int = 0


class BindingPolicy(BaseModel):
    """
    Security policy for agent-MCP bindings.

    Defines what MCPs an agent is allowed/denied to use.
    """

    agent_id: str = Field(..., description="Agent template ID")
    allowed_mcps: list[str] = Field(
        default_factory=list,
        description="List of allowed MCP names (* = all)"
    )
    denied_mcps: list[str] = Field(
        default_factory=list,
        description="List of explicitly denied MCPs"
    )
    max_concurrent_mcps: int = Field(
        10,
        description="Maximum MCPs that can be bound simultaneously"
    )
    require_healthy: bool = Field(
        True,
        description="Require MCP health check before binding"
    )

    def is_allowed(self, mcp_name: str) -> bool:
        """Check if an MCP is allowed by this policy."""
        # Explicit deny takes precedence
        if mcp_name in self.denied_mcps:
            return False

        # Wildcard allows all
        if "*" in self.allowed_mcps:
            return True

        # Check explicit allow
        return mcp_name in self.allowed_mcps
