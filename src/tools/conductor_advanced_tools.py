import logging
import os
import requests # Nova dependência

from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)


class ConductorAdvancedTools:
    """Advanced tools for interacting with the Conductor project via its API."""

    def __init__(self, use_gateway_proxy: bool = True):
        """
        Initialize Conductor tools.

        Args:
            use_gateway_proxy: If True, use localhost:5006/conductor/execute (gateway proxy).
                             If False, use internal conductor-api:8000 directly.
                             Default True for MCP tools to work from outside Docker.
        """
        if use_gateway_proxy:
            # Use gateway proxy - accessible from outside Docker (Gemini MCP)
            self.conductor_api_url = "http://localhost:5006"
        else:
            # Use internal API directly - only works inside Docker network
            self.conductor_api_url = CONDUCTOR_CONFIG.get("conductor_api_url", "http://conductor-api:8000")

        self.timeout = CONDUCTOR_CONFIG.get("timeout", 300) # Timeout padrão para chamadas à API

        logger.info(f"ConductorAdvancedTools inicializado com API URL: {self.conductor_api_url}")

    def _call_conductor_api(self, endpoint: str, method: str = "GET", payload: dict = None, timeout: int = None) -> dict:
        """
        Faz uma chamada HTTP para a Conductor API.
        """
        if timeout is None:
            timeout = self.timeout

        url = f"{self.conductor_api_url}{endpoint}"
        logger.info(f"Chamando Conductor API: {method} {url} com payload: {payload}")

        try:
            if method == "GET":
                response = requests.get(url, params=payload, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, json=payload, timeout=timeout)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")

            response.raise_for_status() # Lança exceção para status de erro (4xx ou 5xx)
            return response.json()

        except requests.exceptions.Timeout:
            error_msg = f"Conductor API excedeu o tempo limite após {timeout} segundos."
            logger.error(error_msg)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 124}
        except requests.exceptions.RequestException as e:
            error_msg = f"Erro ao chamar Conductor API: {e}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 1}
        except Exception as e:
            error_msg = f"Erro inesperado: {e}"
            logger.error(error_msg, exc_info=True)
            return {"status": "error", "stderr": error_msg, "stdout": "", "returncode": 1}

    def _format_response(self, result: dict) -> str:
        """Formata a resposta da API para melhor exibição."""
        try:
            if isinstance(result, dict) and "status" in result:
                if result["status"] == "success":
                    if result.get("stdout"):
                        return result["stdout"]
                    elif result.get("stderr"):
                        return f"⚠️ Aviso:{result['stderr']}"
                    else:
                        return "✅ Comando executado com sucesso!"
                else:
                    if result.get("stderr"):
                        return f"❌ Erro: {result['stderr']}"
                    elif result.get("detail"): # FastAPI errors often use 'detail'
                        return f"❌ Erro: {result['detail']}"
                    else:
                        return "❌ Erro desconhecido"
            elif isinstance(result, dict) and "agents" in result: # Para o endpoint /agents
                agent_names = [agent.get('name', agent.get('id', 'N/A')) for agent in result['agents']]
                return f"🤖 Agentes disponíveis: {', '.join(agent_names)}"
            else:
                return str(result)
        except Exception as e:
            logger.error(f"Erro ao formatar resposta: {e}")
            return f"❌ Erro ao processar resposta: {str(result)[:200]}..."

    def list_available_agents(self) -> str:
        """Lista todos os agentes disponíveis usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {"list_agents": True}
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def execute_agent_stateless(self, agent_id: str, input_text: str, cwd: str, timeout: int = 300) -> dict:
        """
        Executa um agente usando o endpoint genérico do Conductor CLI.
        Preserva o input original do usuário.
        """
        if not agent_id or not input_text or not cwd:
            return {"status": "error", "stderr": "agent_id, input_text e cwd são obrigatórios"}

        endpoint = "/conductor/execute"
        payload = {
            "agent_id": agent_id,
            "input_text": input_text,  # Preserva input original
            "cwd": cwd,
            "timeout": timeout,
            "chat": False  # Modo stateless
        }

        # O timeout da chamada de rede deve ser maior que o timeout da tarefa
        network_timeout = timeout + 20

        result = self._call_conductor_api(
            endpoint=endpoint,
            method="POST",
            payload=payload,
            timeout=network_timeout
        )
        return result

    def get_agent_info(self, agent_id: str) -> str:
        """Obtém informações detalhadas de um agente específico usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {"info_agent": agent_id}
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def validate_conductor_system(self) -> str:
        """Valida a configuração completa do sistema Conductor usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {"validate": True}
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def execute_agent_contextual(self, agent_id: str, input_text: str, timeout: int = 120, clear_history: bool = False) -> dict:
        """Executa um agente mantendo contexto de conversação usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {
            "agent_id": agent_id,
            "input_text": input_text,  # Preserva input original
            "timeout": timeout,
            "chat": True,  # Modo contextual
            "clear_history": clear_history
        }
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload, timeout=timeout + 20)
        return result

    def start_interactive_session(self, agent_id: str, initial_input: str = None, timeout: int = 120) -> dict:
        """Inicia uma sessão interativa com um agente usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {
            "agent_id": agent_id,
            "input_text": initial_input or "Iniciar sessão interativa",
            "timeout": timeout,
            "chat": True,
            "interactive": True
        }
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return result

    def install_agent_templates(self, template_name: str = None) -> str:
        """Instala templates de agentes ou lista templates disponíveis usando API genérica."""
        endpoint = "/conductor/execute"
        if template_name:
            payload = {"install": template_name}
        else:
            payload = {"install": "list"}  # Lista templates disponíveis
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def backup_agents(self, backup_path: str = None) -> str:
        """Faz backup de todos os agentes usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {"backup": True}
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def restore_agents(self, backup_path: str) -> str:
        """Restaura agentes de um backup usando API genérica."""
        endpoint = "/conductor/execute"
        payload = {"restore": backup_path}
        result = self._call_conductor_api(endpoint=endpoint, method="POST", payload=payload)
        return self._format_response(result)

    def migrate_storage(self, from_type: str, to_type: str, path: str = None, no_config_update: bool = False) -> str:
        """Migra storage entre filesystem e MongoDB."""
        payload = {
            "from_type": from_type,
            "to_type": to_type,
            "path": path,
            "no_config_update": no_config_update
        }
        result = self._call_conductor_api(endpoint="/system/migrate", method="POST", payload=payload)
        return self._format_response(result)

    def set_environment(self, environment: str, project: str = None) -> str:
        """Define ambiente e contexto do projeto."""
        payload = {"environment": environment, "project": project}
        result = self._call_conductor_api(endpoint="/system/environment", method="POST", payload=payload)
        return self._format_response(result)

    def get_system_config(self) -> str:
        """Obtém a configuração atual do sistema."""
        result = self._call_conductor_api(endpoint="/system/config", method="GET")
        return self._format_response(result)

    def clear_agent_history(self, agent_id: str) -> str:
        """Limpa o histórico de conversação de um agente."""
        result = self._call_conductor_api(endpoint=f"/sessions/{agent_id}/history", method="DELETE")
        return self._format_response(result)
