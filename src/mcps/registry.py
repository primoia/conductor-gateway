"""
MCP Registry - Mapping of MCP names to ports and configurations.

This registry is the single source of truth for MCP server configurations.
When adding a new MCP, add it here first.
"""

import os
from typing import TypedDict


class MCPConfig(TypedDict, total=False):
    port: int
    description: str
    target_url: str | None  # None for internal services like database
    puppeteer_url: str | None  # For Prospector offline operations


# MCP Registry - Single source of truth for all MCP configurations
# Ports start at 5007 (5006 is the BFF)
MCP_REGISTRY: dict[str, MCPConfig] = {
    "prospector": {
        "port": int(os.getenv("MCP_PROSPECTOR_PORT", "5007")),
        "description": "Web scraping and contact extraction",
        "target_url": os.getenv("PROSPECTOR_URL", "http://prospector-orchestrator:8081"),
        "puppeteer_url": os.getenv("PUPPETEER_URL", "http://primoia-prospector-puppeteer:3001"),
    },
    "database": {
        "port": int(os.getenv("MCP_DATABASE_PORT", "5008")),
        "description": "MongoDB operations for leads and data storage",
        "target_url": None,  # Uses internal MongoDB connection
    },
    "conductor": {
        "port": int(os.getenv("MCP_CONDUCTOR_PORT", "5009")),
        "description": "Execute Conductor agents",
        "target_url": os.getenv("CONDUCTOR_API_URL", "http://conductor-api:8000"),
    },
    "observations": {
        "port": int(os.getenv("MCP_OBSERVATIONS_PORT", "5010")),
        "description": "Task observations for dynamic world_state injection",
        "target_url": os.getenv("CONDUCTOR_API_URL", "http://conductor-api:8000"),
    },
}


def get_mcp_port(name: str) -> int | None:
    """Get the port for an MCP by name."""
    config = MCP_REGISTRY.get(name)
    return config["port"] if config else None


def get_mcp_config(name: str) -> MCPConfig | None:
    """Get the full configuration for an MCP by name."""
    return MCP_REGISTRY.get(name)


def get_all_mcp_names() -> list[str]:
    """Get all registered MCP names."""
    return list(MCP_REGISTRY.keys())


def get_all_mcp_ports() -> dict[str, int]:
    """Get mapping of all MCP names to their ports."""
    return {name: config["port"] for name, config in MCP_REGISTRY.items()}
