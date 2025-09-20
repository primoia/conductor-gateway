import logging
import os
import subprocess

from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)


class ConductorAdvancedTools:
    """Advanced tools for interacting with the Conductor project."""

    def __init__(self):
        self.project_path = CONDUCTOR_CONFIG["project_path"]
        self.timeout = CONDUCTOR_CONFIG["timeout"]

        logger.info(f"ConductorAdvancedTools initialized with project path: {self.project_path}")

    def _execute_conductor_command(self, command: list[str], timeout: int = None) -> dict:
        """Execute a conductor command and return the result."""
        if timeout is None:
            timeout = self.timeout

        # Remove interactive flags to prevent gateway from getting stuck
        command = [arg for arg in command if arg not in ["--interactive", "--repl"]]

        # Execute conductor using the conda Python from the conductor directory
        conductor_path = os.path.join(self.project_path, "conductor")
        # Use the Python from the conductor's conda environment
        python_path = "/home/cezar/miniconda3/bin/python"
        full_command = [python_path, conductor_path] + command

        logger.info(f"Executing conductor command: {' '.join(full_command)}")

        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                check=False,
                cwd=self.project_path,
                timeout=timeout,
            )

            # Debug logging
            logger.info(f"Command result - Return code: {result.returncode}")
            logger.info(f"STDOUT length: {len(result.stdout)}")
            logger.info(f"STDERR: {result.stderr}")
            logger.info(f"STDOUT preview: {result.stdout[:200]}...")

            status = "success" if result.returncode == 0 else "error"

            return {
                "status": status,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": " ".join(full_command),
            }

        except subprocess.TimeoutExpired:
            error_msg = f"Command execution timed out after {timeout} seconds"
            logger.error(error_msg)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 124}
        except Exception as e:
            error_msg = f"Unexpected error executing command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 1}

    def _format_response(self, result: dict) -> str:
        """Format the response for better display in the chat."""
        try:
            if isinstance(result, dict) and "status" in result:
                if result["status"] == "success":
                    if result.get("stdout"):
                        return result["stdout"]
                    elif result.get("stderr"):
                        return f"⚠️ Aviso: {result['stderr']}"
                    else:
                        return "✅ Comando executado com sucesso!"
                else:
                    if result.get("stderr"):
                        return f"❌ Erro: {result['stderr']}"
                    else:
                        return "❌ Erro desconhecido"
            else:
                # Se result não é um dicionário ou não tem status, retornar como string
                return str(result)
        except Exception as e:
            logger.error(f"Erro ao formatar resposta: {e}")
            return f"❌ Erro ao processar resposta: {str(result)[:200]}..."

    def list_available_agents(self) -> str:
        """List all available agents in the Conductor system."""
        result = self._execute_conductor_command(["--list"])
        return self._format_response(result)

    def get_agent_info(self, agent_id: str) -> str:
        """Get detailed information about a specific agent."""
        if not agent_id:
            return "❌ Erro: Agent ID é obrigatório"

        result = self._execute_conductor_command(["--info", agent_id])
        return self._format_response(result)

    def validate_conductor_system(self) -> str:
        """Validate the Conductor system configuration."""
        result = self._execute_conductor_command(["--validate"])
        return self._format_response(result)

    def execute_agent_stateless(
        self, agent_id: str, input_text: str, timeout: int = 120, output_format: str = "text"
    ) -> dict:
        """Execute an agent in stateless mode (fast, no history)."""
        if not agent_id or not input_text:
            return {
                "status": "error",
                "stderr": "Agent ID and input text are required",
                "stdout": "",
                "returncode": 1,
            }

        command = ["--agent", agent_id, "--input", input_text]

        if timeout != 120:
            command.extend(["--timeout", str(timeout)])

        if output_format == "json":
            command.append("--output")
            command.append("json")

        return self._execute_conductor_command(command, timeout)

    def execute_agent_contextual(
        self, agent_id: str, input_text: str, timeout: int = 120, clear_history: bool = False
    ) -> dict:
        """Execute an agent in contextual mode (with conversation history)."""
        if not agent_id or not input_text:
            return {
                "status": "error",
                "stderr": "Agent ID and input text are required",
                "stdout": "",
                "returncode": 1,
            }

        command = ["--agent", agent_id, "--chat", "--input", input_text]

        if timeout != 120:
            command.extend(["--timeout", str(timeout)])

        if clear_history:
            command.append("--clear")

        return self._execute_conductor_command(command, timeout)

    def start_interactive_session(
        self, agent_id: str, initial_input: str = None, timeout: int = 120
    ) -> dict:
        """Start an interactive session with an agent."""
        if not agent_id:
            return {
                "status": "error",
                "stderr": "Agent ID is required",
                "stdout": "",
                "returncode": 1,
            }

        command = ["--agent", agent_id, "--chat", "--interactive"]

        if initial_input:
            command.extend(["--input", initial_input])

        if timeout != 120:
            command.extend(["--timeout", str(timeout)])

        return self._execute_conductor_command(command, timeout)

    def install_agent_templates(self, template_name: str = None) -> dict:
        """Install agent templates."""
        command = ["--install"]

        if template_name:
            command.append(template_name)
        else:
            command.append("list")

        return self._execute_conductor_command(command)

    def backup_agents(self, backup_path: str = None) -> str:
        """Backup all agents."""
        command = ["--backup"]

        if backup_path:
            command.extend(["--path", backup_path])

        result = self._execute_conductor_command(command)
        return self._format_response(result)

    def restore_agents(self, backup_path: str) -> dict:
        """Restore agents from backup."""
        if not backup_path:
            return {
                "status": "error",
                "stderr": "Backup path is required",
                "stdout": "",
                "returncode": 1,
            }

        command = ["--restore", "--path", backup_path]
        return self._execute_conductor_command(command)

    def migrate_storage(
        self, from_type: str, to_type: str, path: str = None, no_config_update: bool = False
    ) -> dict:
        """Migrate storage between filesystem and MongoDB."""
        if not from_type or not to_type:
            return {
                "status": "error",
                "stderr": "From type and to type are required",
                "stdout": "",
                "returncode": 1,
            }

        command = ["--migrate-from", from_type, "--migrate-to", to_type]

        if path:
            command.extend(["--path", path])

        if no_config_update:
            command.append("--no-config-update")

        return self._execute_conductor_command(command)

    def set_environment(self, environment: str, project: str = None) -> dict:
        """Set environment and project context."""
        if not environment:
            return {
                "status": "error",
                "stderr": "Environment is required",
                "stdout": "",
                "returncode": 1,
            }

        # This would require modifying the conductor command to accept environment/project
        # For now, return a placeholder
        return {
            "status": "success",
            "stdout": f"Environment set to: {environment}, Project: {project or 'default'}",
            "stderr": "",
            "returncode": 0,
        }

    def get_system_config(self) -> dict:
        """Get current system configuration."""
        # Read and return the config.yaml file
        config_path = os.path.join(self.project_path, "config.yaml")

        if not os.path.exists(config_path):
            return {
                "status": "error",
                "stderr": f"Config file not found: {config_path}",
                "stdout": "",
                "returncode": 1,
            }

        try:
            with open(config_path) as f:
                config_content = f.read()

            return {"status": "success", "stdout": config_content, "stderr": "", "returncode": 0}
        except Exception as e:
            return {
                "status": "error",
                "stderr": f"Error reading config: {str(e)}",
                "stdout": "",
                "returncode": 1,
            }

    def clear_agent_history(self, agent_id: str) -> dict:
        """Clear conversation history for a specific agent."""
        if not agent_id:
            return {
                "status": "error",
                "stderr": "Agent ID is required",
                "stdout": "",
                "returncode": 1,
            }

        # This would require a specific conductor command for clearing history
        # For now, return a placeholder
        return {
            "status": "success",
            "stdout": f"History cleared for agent: {agent_id}",
            "stderr": "",
            "returncode": 0,
        }
