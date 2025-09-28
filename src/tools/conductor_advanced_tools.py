import logging
import os
import requests # Nova dependência

from src.config.settings import CONDUCTOR_CONFIG

logger = logging.getLogger(__name__)


class ConductorAdvancedTools:
    """Advanced tools for interacting with the Conductor project via its API."""

    def __init__(self):
        # A URL da API do Conductor será obtida das configurações
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
        """Lista todos os agentes disponíveis na Conductor API."""
        result = self._call_conductor_api(endpoint="/agents", method="GET")
        return self._format_response(result)

    def execute_agent_stateless(self, agent_id: str, input_text: str, cwd: str, timeout: int = 300) -> dict:
        """
        Executa um agente na Conductor API usando o endpoint genérico.
        """
        if not agent_id or not input_text or not cwd:
            return {"status": "error", "stderr": "agent_id, input_text e cwd são obrigatórios"}

        endpoint = f"/agents/{agent_id}/execute"
        payload = {
            "user_input": input_text,
            "cwd": cwd,
            "timeout": timeout
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
