import os
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient
import logging
import time

logger = logging.getLogger(__name__)

def init_agent(agent_config: dict):
    """
    Inicializa o agente MCP com uma configuração completa fornecida.
    :param agent_config: Um dicionário contendo a configuração completa para MCPClient.from_dict().
    """
    retries = 3
    retry_delay = 2  # segundos

    logger.info("Variáveis de ambiente disponíveis: %s", list(os.environ.keys()))
    
    while retries > 0:
        try:
            if not agent_config or "mcpServers" not in agent_config:
                raise ValueError("A configuração do agente está incompleta ou vazia.")
            
            logger.info("Tentando inicializar cliente MCP com a seguinte configuração: %s", agent_config)
            client = MCPClient.from_dict(agent_config)
            
            # Configuração do modelo LLM
            credential = os.environ.get("OPENAI_API_KEY")
            logger.info("OPENAI_API_KEY presente: %s", "Sim" if credential else "Não")
            
            llm = ChatOpenAI(
                model="gpt-4.1-mini",
                openai_api_key=credential
            )

            agent = MCPAgent(llm=llm, client=client, max_steps=30)
            logger.info("Agente MCP inicializado com sucesso!")
            return agent

        except Exception as e:
            retries -= 1
            if retries > 0:
                logger.warning(f"Falha ao inicializar agente MCP. Tentando novamente em {retry_delay} segundos... ({e})")
                time.sleep(retry_delay)
            else:
                logger.error(f"Falha ao inicializar agente MCP após todas as tentativas: {e}")
                raise
    return None 