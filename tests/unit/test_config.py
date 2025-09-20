"""
Tests for configuration management.
"""

import os
from unittest.mock import mock_open, patch

import pytest

from src.config.settings import CONDUCTOR_CONFIG, SERVER_CONFIG, load_config


@pytest.mark.unit
class TestConfigurationLoading:
    """Test configuration loading functionality."""

    def test_load_config_with_yaml_file(self, temp_config_file):
        """Test loading configuration from YAML file."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=open(temp_config_file).read())),
        ):
            config = load_config()

            assert config["server"]["host"] == "127.0.0.1"
            assert config["server"]["port"] == 5006
            assert config["server"]["mcp_port"] == 8006
            assert config["conductor"]["project_path"] == "/tmp/test_conductor"

    def test_load_config_fallback_to_defaults(self):
        """Test configuration fallback when YAML file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            config = load_config()

            # Should have default values
            assert "server" in config
            assert "conductor" in config
            assert config["server"]["host"] == "0.0.0.0"
            assert config["server"]["port"] == 5006

    def test_environment_variable_override(self, temp_config_file):
        """Test that environment variables override config file values."""
        with (
            patch.dict(
                os.environ,
                {
                    "HOST": "192.168.1.100",
                    "PORT": "9000",
                    "CONDUCTOR_PROJECT_PATH": "/custom/conductor/path",
                },
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            config = load_config()

            assert config["server"]["host"] == "192.168.1.100"
            assert config["server"]["port"] == 9000
            assert config["conductor"]["project_path"] == "/custom/conductor/path"

    def test_invalid_yaml_file(self):
        """Test handling of invalid YAML file."""
        invalid_yaml = "invalid: yaml: content: ["

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=invalid_yaml)),
        ):
            config = load_config()

            # Should fall back to defaults
            assert config["server"]["host"] == "0.0.0.0"

    def test_server_config_constants(self):
        """Test that SERVER_CONFIG is properly initialized."""
        assert "host" in SERVER_CONFIG
        assert "port" in SERVER_CONFIG
        assert "mcp_port" in SERVER_CONFIG
        assert isinstance(SERVER_CONFIG["port"], int)
        assert isinstance(SERVER_CONFIG["mcp_port"], int)

    def test_conductor_config_constants(self):
        """Test that CONDUCTOR_CONFIG is properly initialized."""
        assert "project_path" in CONDUCTOR_CONFIG
        assert "timeout" in CONDUCTOR_CONFIG
        assert isinstance(CONDUCTOR_CONFIG["project_path"], str)
        assert isinstance(CONDUCTOR_CONFIG["timeout"], int)

    @pytest.mark.parametrize(
        "env_var,config_path,expected",
        [
            ("HOST", ["server", "host"], "test.host"),
            ("PORT", ["server", "port"], 8888),
            ("MCP_PORT", ["server", "mcp_port"], 9999),
            ("CONDUCTOR_PROJECT_PATH", ["conductor", "project_path"], "/test/path"),
            ("CONDUCTOR_TIMEOUT", ["conductor", "timeout"], 600),
        ],
    )
    def test_environment_variable_mapping(self, env_var, config_path, expected, temp_config_file):
        """Test that environment variables correctly map to config paths."""
        with (
            patch.dict(os.environ, {env_var: str(expected)}),
            patch("pathlib.Path.exists", return_value=False),
        ):
            config = load_config()

            # Navigate to the config value using the path
            value = config
            for key in config_path:
                value = value[key]

            # Convert to appropriate type for comparison
            if isinstance(expected, int):
                assert value == expected
            else:
                assert value == expected
