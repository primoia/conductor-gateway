"""
MCP Utilities for agent initialization and configuration.

Provides functions to:
- Resolve MCP names to URLs via the MCP Registry
- Build mcpServers configuration for MCPAgent
- Initialize MCPAgent with dynamic MCP configuration
"""

import logging
import os
import time
from typing import Optional

from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

logger = logging.getLogger(__name__)


def resolve_mcp_configs(mcp_names: list[str], registry_service=None) -> dict[str, str]:
    """
    Resolve MCP names to URLs using the MCP Registry.

    Args:
        mcp_names: List of MCP names to resolve (e.g., ["crm", "billing", "prospector"])
        registry_service: Optional MCPRegistryService instance (uses global if not provided)

    Returns:
        Dict mapping MCP names to their SSE URLs
    """
    if not mcp_names:
        return {}

    # If registry service provided, use it directly
    if registry_service:
        resolved, not_found = registry_service.resolve_names(mcp_names)
        if not_found:
            logger.warning(f"Could not resolve MCPs: {not_found}")
        return resolved

    # Otherwise, try to get from global service
    try:
        from src.api.routers.mcp_registry import get_registry_service
        service = get_registry_service()
        resolved, not_found = service.resolve_names(mcp_names)
        if not_found:
            logger.warning(f"Could not resolve MCPs: {not_found}")
        return resolved
    except Exception as e:
        logger.warning(f"Could not access MCP Registry: {e}")
        return {}


def build_mcp_servers_config(
    mcp_names: Optional[list[str]] = None,
    legacy_mcp_url: Optional[str] = None,
    registry_service=None
) -> dict:
    """
    Build the mcpServers configuration for MCPAgent.

    Combines:
    - Legacy MCP URL (for backwards compatibility)
    - Resolved MCP names from registry

    Args:
        mcp_names: List of MCP names to resolve and include
        legacy_mcp_url: Legacy MCP URL to include (e.g., internal conductor MCP)
        registry_service: Optional MCPRegistryService instance

    Returns:
        Dict in format {"mcpServers": {"name": {"url": "...", "transport": "sse"}}}
    """
    mcp_servers = {}

    # Add legacy MCP if provided (backwards compatibility)
    if legacy_mcp_url:
        mcp_servers["conductor"] = {
            "url": legacy_mcp_url,
            "transport": "sse"
        }

    # Resolve and add named MCPs
    if mcp_names:
        resolved = resolve_mcp_configs(mcp_names, registry_service)
        for name, url in resolved.items():
            mcp_servers[name] = {
                "url": url,
                "transport": "sse"
            }
            logger.info(f"Added MCP '{name}' -> {url}")

    return {"mcpServers": mcp_servers}


def init_agent(agent_config: dict):
    """
    Inicializa o agente MCP com uma configuração completa fornecida.

    Args:
        agent_config: Um dicionário contendo a configuração completa para MCPClient.from_dict().
                     Deve conter "mcpServers" com os servidores MCP configurados.

    Returns:
        MCPAgent instance or None if initialization fails
    """
    retries = 3
    retry_delay = 2  # segundos

    logger.info("Variáveis de ambiente disponíveis: %s", list(os.environ.keys()))

    while retries > 0:
        try:
            if not agent_config or "mcpServers" not in agent_config:
                raise ValueError("A configuração do agente está incompleta ou vazia.")

            logger.info(
                "Tentando inicializar cliente MCP com a seguinte configuração: %s", agent_config
            )
            client = MCPClient.from_dict(agent_config)

            # Configuração do modelo LLM
            credential = os.environ.get("OPENAI_API_KEY")
            logger.info("OPENAI_API_KEY presente: %s", "Sim" if credential else "Não")

            llm = ChatOpenAI(model="gpt-4.1-mini", openai_api_key=credential)  # type: ignore

            agent = MCPAgent(llm=llm, client=client, max_steps=30)
            logger.info("Agente MCP inicializado com sucesso!")
            return agent

        except Exception as e:
            retries -= 1
            if retries > 0:
                logger.warning(
                    f"Falha ao inicializar agente MCP. Tentando novamente em {retry_delay} segundos... ({e})"
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"Falha ao inicializar agente MCP após todas as tentativas: {e}")
                raise
    return None


def init_agent_with_mcps(
    mcp_names: Optional[list[str]] = None,
    legacy_mcp_url: Optional[str] = None,
    registry_service=None
):
    """
    Initialize an MCPAgent with dynamically resolved MCP configurations.

    This is the preferred way to initialize agents when you have MCP names
    instead of hardcoded URLs.

    Args:
        mcp_names: List of MCP names to include (e.g., ["crm", "billing"])
        legacy_mcp_url: Optional legacy MCP URL for backwards compatibility
        registry_service: Optional MCPRegistryService instance

    Returns:
        MCPAgent instance or None if initialization fails

    Example:
        # Agent that can use CRM and Billing MCPs
        agent = init_agent_with_mcps(
            mcp_names=["crm", "billing"],
            legacy_mcp_url="http://localhost:8006/sse"
        )
    """
    agent_config = build_mcp_servers_config(
        mcp_names=mcp_names,
        legacy_mcp_url=legacy_mcp_url,
        registry_service=registry_service
    )

    if not agent_config.get("mcpServers"):
        logger.error("No MCP servers configured - cannot initialize agent")
        return None

    logger.info(f"Initializing agent with {len(agent_config['mcpServers'])} MCP servers")
    return init_agent(agent_config)
