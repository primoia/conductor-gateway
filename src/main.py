"""
Conductor Gateway - Main Entry Point
"""

import logging
import threading

import uvicorn

from api.app import create_app
from config.settings import CONDUCTOR_CONFIG, SERVER_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def start_mcp_server():
    """Starts MCP server in a separate thread."""
    try:
        logger.info("Starting MCP server thread...")
        from server.advanced_server import ConductorAdvancedMCPServer

        server = ConductorAdvancedMCPServer(port=SERVER_CONFIG["mcp_port"])
        server.run(transport="sse")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}", exc_info=True)


def main():
    """Main application entry point."""
    logger.info("Starting Conductor Gateway...")
    logger.info(f"Server will run on {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    logger.info(f"MCP server will run on port {SERVER_CONFIG['mcp_port']}")
    logger.info(f"Conductor project path: {CONDUCTOR_CONFIG['project_path']}")

    # Start MCP server in background thread
    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
    mcp_thread.start()

    # Create FastAPI app
    app = create_app()

    # Run the server
    uvicorn.run(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"], log_level="info")


if __name__ == "__main__":
    main()
