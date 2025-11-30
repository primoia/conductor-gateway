"""
Modelos Pydantic para API do Gateway
"""

from typing import Any, Optional
from pydantic import BaseModel


class AgentExecuteRequest(BaseModel):
    """Payload para execução de agente."""

    input_text: str
    instance_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context_mode: str = "stateless"
    cwd: Optional[str] = None
    screenplay_id: Optional[str] = None
    document_id: Optional[str] = None  # Deprecated, mantido para compatibilidade
    position: Optional[dict[str, Any]] = None
    ai_provider: Optional[str] = None


class TaskSubmitRequest(BaseModel):
    """
    Payload para submissão de task com observabilidade imediata.

    O frontend gera o task_id antes de enviar, permitindo rastrear
    a task desde o momento do input do usuário.
    """

    task_id: str  # UUID gerado pelo frontend
    agent_id: str
    agent_name: str
    agent_emoji: str = "🤖"
    instance_id: str
    conversation_id: str
    screenplay_id: Optional[str] = None
    input_text: str
    cwd: Optional[str] = None
    ai_provider: Optional[str] = "claude"
