"""
Conductor Gateway - Main Entry Point
"""

import logging

import uvicorn

from src.api.app import create_app
from src.config.settings import CONDUCTOR_CONFIG, SERVER_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main application entry point."""
    logger.info("Starting Conductor Gateway...")
    logger.info(f"Server will run on {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    logger.info(f"MCP server will run on port {SERVER_CONFIG['mcp_port']}")
    logger.info(f"Conductor project path: {CONDUCTOR_CONFIG['project_path']}")

    # Create FastAPI app (MCP server will be started by the app's lifespan handler)
    app = create_app()

    # Run the server
    uvicorn.run(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"], log_level="info")


if __name__ == "__main__":
    main()