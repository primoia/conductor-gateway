import logging

from mcp.server import FastMCP

from tools.conductor_advanced_tools import ConductorAdvancedTools

logger = logging.getLogger(__name__)


class ConductorAdvancedMCPServer:
    """Advanced MCP Server for Conductor Gateway with full Conductor CLI support."""

    def __init__(self, port: int):
        self.mcp = FastMCP(name="ConductorAdvancedMCP")
        self.port = port
        self.advanced_tools = ConductorAdvancedTools()
        self._register_advanced_tools()

        logger.info(f"ConductorAdvancedMCPServer initialized on port {port}")

    def _register_advanced_tools(self):
        """Register all advanced tools with the MCP server."""

        # === BASIC COMMANDS ===

        # List available agents
        self.mcp.tool(
            name="list_available_agents",
            description="""Lists all available agents in the Conductor system.
            
            Returns a list of all agents with their capabilities and tags.""",
        )(self.advanced_tools.list_available_agents)

        # Get agent information
        self.mcp.tool(
            name="get_agent_info",
            description="""Get detailed information about a specific agent.
            Parameters:
            - agent_id: The ID of the agent to get information for
            
            Returns complete agent information including capabilities, tags, and status.""",
        )(self.advanced_tools.get_agent_info)

        # Validate system
        self.mcp.tool(
            name="validate_conductor_system",
            description="""Validate the Conductor system configuration.
            
            Returns validation results and any configuration issues.""",
        )(self.advanced_tools.validate_conductor_system)

        # === AGENT EXECUTION ===

        # Stateless execution
        self.mcp.tool(
            name="execute_agent_stateless",
            description="""Execute an agent in stateless mode (fast, no history).
            Parameters:
            - agent_id: The ID of the agent to execute
            - input_text: The input text for the agent
            - timeout: Execution timeout in seconds (default: 120)
            - output_format: Output format - 'text' or 'json' (default: 'text')
            
            Returns the agent's response without maintaining conversation history.""",
        )(self.advanced_tools.execute_agent_stateless)

        # Contextual execution
        self.mcp.tool(
            name="execute_agent_contextual",
            description="""Execute an agent in contextual mode (with conversation history).
            Parameters:
            - agent_id: The ID of the agent to execute
            - input_text: The input text for the agent
            - timeout: Execution timeout in seconds (default: 120)
            - clear_history: Whether to clear conversation history (default: False)
            
            Returns the agent's response while maintaining conversation context.""",
        )(self.advanced_tools.execute_agent_contextual)

        # Interactive session
        self.mcp.tool(
            name="start_interactive_session",
            description="""Start an interactive session with an agent.
            Parameters:
            - agent_id: The ID of the agent to start session with
            - initial_input: Optional initial input for the session
            - timeout: Session timeout in seconds (default: 120)
            
            Returns session initialization result.""",
        )(self.advanced_tools.start_interactive_session)

        # === SYSTEM MANAGEMENT ===

        # Install templates
        self.mcp.tool(
            name="install_agent_templates",
            description="""Install agent templates.
            Parameters:
            - template_name: Name of template to install (optional, lists available if not provided)
            
            Returns installation results or list of available templates.""",
        )(self.advanced_tools.install_agent_templates)

        # Backup agents
        self.mcp.tool(
            name="backup_agents",
            description="""Backup all agents.
            Parameters:
            - backup_path: Optional path for backup (uses default if not provided)
            
            Returns backup operation results.""",
        )(self.advanced_tools.backup_agents)

        # Restore agents
        self.mcp.tool(
            name="restore_agents",
            description="""Restore agents from backup.
            Parameters:
            - backup_path: Path to the backup to restore from
            
            Returns restore operation results.""",
        )(self.advanced_tools.restore_agents)

        # Migrate storage
        self.mcp.tool(
            name="migrate_storage",
            description="""Migrate storage between filesystem and MongoDB.
            Parameters:
            - from_type: Source storage type ('filesystem' or 'mongodb')
            - to_type: Target storage type ('filesystem' or 'mongodb')
            - path: Optional path for migration
            - no_config_update: Whether to skip config file update (default: False)
            
            Returns migration operation results.""",
        )(self.advanced_tools.migrate_storage)

        # === CONFIGURATION ===

        # Set environment
        self.mcp.tool(
            name="set_environment",
            description="""Set environment and project context.
            Parameters:
            - environment: Environment name to set
            - project: Optional project name
            
            Returns environment setting results.""",
        )(self.advanced_tools.set_environment)

        # Get system config
        self.mcp.tool(
            name="get_system_config",
            description="""Get current system configuration.
            
            Returns the contents of the config.yaml file.""",
        )(self.advanced_tools.get_system_config)

        # Clear agent history
        self.mcp.tool(
            name="clear_agent_history",
            description="""Clear conversation history for a specific agent.
            Parameters:
            - agent_id: The ID of the agent to clear history for
            
            Returns history clearing results.""",
        )(self.advanced_tools.clear_agent_history)

        logger.info("All advanced tools registered successfully")

    def run(self, transport="sse"):
        """Start the advanced MCP server."""
        try:
            logger.info(
                f"Starting advanced MCP server on port {self.port} with {transport} transport"
            )
            self.mcp.run(transport=transport)
        except Exception as e:
            logger.error(f"Failed to start advanced MCP server: {str(e)}", exc_info=True)
            raise
