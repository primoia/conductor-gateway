import logging
import os
from pathlib import Path

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from YAML file with environment variable overrides."""
    # Default configuration
    config = {
        "server": {"host": "0.0.0.0", "port": 5006, "mcp_port": 8006},
        "conductor": {
            "project_path": "/mnt/ramdisk/primoia-main/primoia-monorepo/projects/conductor",
            "scripts_path": "scripts",
            "timeout": 1800,
            "conductor_api_url": "http://conductor-api:8000",
        },
        "mongodb": {
            "url": os.getenv("MONGODB_URL", "mongodb://admin:czrimr@mongodb:27017/?authSource=admin"),
            "database": "conductor_state",
        },
    }

    # Load from YAML file if it exists
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    # Merge YAML config with defaults
                    config.update(yaml_config)
                    logger.info(f"Configuration loaded from: {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config.yaml: {e}")
    else:
        logger.info("No config.yaml found, using defaults")

    # Override with environment variables
    config["server"]["host"] = os.getenv("HOST", config["server"]["host"])
    config["server"]["port"] = int(os.getenv("PORT", config["server"]["port"]))
    config["server"]["mcp_port"] = int(os.getenv("MCP_PORT", config["server"]["mcp_port"]))

    config["conductor"]["project_path"] = os.getenv(
        "CONDUCTOR_PROJECT_PATH", config["conductor"]["project_path"]
    )
    config["conductor"]["scripts_path"] = os.getenv(
        "CONDUCTOR_SCRIPTS_PATH", config["conductor"]["scripts_path"]
    )
    config["conductor"]["timeout"] = int(
        os.getenv("CONDUCTOR_TIMEOUT", config["conductor"]["timeout"])
    )
    config["conductor"]["conductor_api_url"] = os.getenv(
        "CONDUCTOR_API_URL", config["conductor"]["conductor_api_url"]
    )

    config["mongodb"]["url"] = os.getenv("MONGODB_URL", config["mongodb"]["url"])
    config["mongodb"]["database"] = os.getenv("MONGODB_DATABASE", config["mongodb"]["database"])

    return config


# Load configuration
_config = load_config()

# Extract configurations for backward compatibility
SERVER_CONFIG = _config["server"]
CONDUCTOR_CONFIG = _config["conductor"]
MONGODB_CONFIG = _config["mongodb"]

logger.info(f"Server will run on {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
logger.info(f"MCP server will run on port {SERVER_CONFIG['mcp_port']}")
logger.info(f"Conductor project path: {CONDUCTOR_CONFIG['project_path']}")
logger.info(f"MongoDB: {MONGODB_CONFIG['url']}/{MONGODB_CONFIG['database']}")


# MongoDB client singleton
_mongo_client = None


def get_mongodb_client():
    """
    Get MongoDB client singleton.
    Creates client on first call, reuses on subsequent calls.
    """
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient(MONGODB_CONFIG["url"])
        logger.info(f"MongoDB client created for {MONGODB_CONFIG['url']}")
    return _mongo_client
